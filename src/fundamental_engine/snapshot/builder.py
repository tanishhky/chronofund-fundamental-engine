"""
builder.py – Main snapshot build orchestrator for EDGAR data.

The entry point is ``build_edgar_snapshot()``. It:
1. Resolves tickers → CIKs
2. Fetches filing lists (PIT-filtered)
3. Selects best filing per period
4. Fetches and parses XBRL facts
5. Assembles DataFrames for all statement types
6. Computes derived metrics
7. Runs accounting identity checks
8. Returns a SnapshotResult
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

import pandas as pd

from fundamental_engine.config import EngineConfig
from fundamental_engine.config_resolver import resolve_config
from fundamental_engine.data.schema import (
    BALANCE_SCHEMA,
    CASHFLOW_SCHEMA,
    COMPANY_MASTER_SCHEMA,
    DERIVED_SCHEMA,
    FILINGS_SCHEMA,
    INCOME_SCHEMA,
)
from fundamental_engine.data.validation import (
    check_balance_sheet_identity,
    check_cashflow_reconciliation,
)
from fundamental_engine.edgar.cik_map import CIKMapper
from fundamental_engine.edgar.client import EdgarClient
from fundamental_engine.edgar.filings_index import FilingsIndex
from fundamental_engine.edgar.xbrl.fetch import XBRLFetcher
from fundamental_engine.edgar.xbrl.parser import XBRLParser
from fundamental_engine.exceptions import FilingNotFoundError
from fundamental_engine.snapshot.coverage import build_coverage_report
from fundamental_engine.snapshot.selector import FilingSelector
from fundamental_engine.types import (
    CoverageReport,
    FilingPeriodType,
    FilingRecord,
    SnapshotRequest,
    SnapshotResult,
)

logger = logging.getLogger(__name__)


def build_edgar_snapshot(
    request: SnapshotRequest,
    config: EngineConfig | None = None,
) -> SnapshotResult:
    """
    Build a full point-in-time fundamental data snapshot from SEC EDGAR.

    This is the top-level entry point for EDGAR-sourced data.

    Parameters
    ----------
    request:
        SnapshotRequest describing tickers, cutoff date, and options.
    config:
        Engine configuration. If None, loads from environment.

    Returns
    -------
    SnapshotResult containing all standardized tables and coverage report.
    """
    cfg = config or EngineConfig.from_env()
    resolved = resolve_config(request, cfg)
    resolved.assert_pit_safe()  # Fail fast if allow_estimates=True

    with EdgarClient(cfg) as client:
        cik_mapper = CIKMapper(client)
        cik_mapper.load()

        filings_index = FilingsIndex(client, cfg)
        # Pass resolved config so FilingSelector uses the unified allow_amendments flag
        selector = FilingSelector(cfg, allow_amendments=resolved.allow_amendments)
        xbrl_fetcher = XBRLFetcher(client)

        # Resolve tickers to CIKs
        cik_map = cik_mapper.resolve_many(request.tickers)
        logger.info(
            "Resolved %d/%d tickers to CIKs",
            len(cik_map), len(request.tickers),
        )

        # Build master table
        company_rows = []
        for ticker, cik in cik_map.items():
            company_rows.append({
                "ticker": ticker,
                "cik": cik,
                "company_name": cik_mapper.company_name(ticker) or "",
                "sic": None,
                "exchange": None,
            })
        company_df = pd.DataFrame(company_rows)

        all_income: list[dict] = []
        all_balance: list[dict] = []
        all_cashflow: list[dict] = []
        all_filings: list[dict] = []

        annual = request.period_type == FilingPeriodType.ANNUAL

        for ticker, cik in cik_map.items():
            try:
                logger.info("Processing ticker=%s cik=%s", ticker, cik)
                raw_filings = filings_index.get_filings(
                    cik=cik,
                    ticker=ticker,
                    cutoff_date=request.cutoff_date,
                    period_type=request.period_type,
                )
                selected = selector.select(raw_filings, request.cutoff_date)

                # Fetch XBRL facts once per CIK
                facts = xbrl_fetcher.fetch_all_facts(cik)
                parser = XBRLParser(ticker=ticker, cik=cik)

                for filing in selected:
                    # Record filing metadata
                    all_filings.append({
                        "ticker": ticker,
                        "cik": cik,
                        "accession": filing.accession,
                        "form_type": filing.form_type,
                        "filing_date": filing.filing_date,
                        "acceptance_datetime": filing.acceptance_datetime,
                        "period_of_report": filing.period_of_report,
                        "source": "edgar",
                    })

                    asof = filing.acceptance_datetime.date()
                    period_end = filing.period_of_report

                    income_row = parser.build_income_rows(
                        facts=facts,
                        filing_accession=filing.accession,
                        period_end=period_end,
                        cutoff_date=request.cutoff_date,
                        asof_date=asof,
                        annual=annual,
                    )
                    if income_row:
                        all_income.append(income_row)

                    balance_row = parser.build_balance_rows(
                        facts=facts,
                        filing_accession=filing.accession,
                        period_end=period_end,
                        cutoff_date=request.cutoff_date,
                        asof_date=asof,
                    )
                    if balance_row:
                        all_balance.append(balance_row)

                    cashflow_row = parser.build_cashflow_rows(
                        facts=facts,
                        filing_accession=filing.accession,
                        period_end=period_end,
                        cutoff_date=request.cutoff_date,
                        asof_date=asof,
                        annual=annual,
                    )
                    if cashflow_row:
                        all_cashflow.append(cashflow_row)

            except FilingNotFoundError:
                logger.warning("No qualifying filings found for %s at cutoff %s",
                               ticker, request.cutoff_date)
            except Exception as exc:
                logger.error("Error processing ticker=%s: %s", ticker, exc, exc_info=True)

    # Assemble DataFrames
    income_df = _assemble_df(all_income, INCOME_SCHEMA)
    balance_df = _assemble_df(all_balance, BALANCE_SCHEMA)
    cashflow_df = _assemble_df(all_cashflow, CASHFLOW_SCHEMA)
    filings_df = _assemble_df(all_filings, FILINGS_SCHEMA)

    # Accounting checks
    balance_df = check_balance_sheet_identity(balance_df)
    cashflow_df = check_cashflow_reconciliation(cashflow_df)

    # Compute derived metrics
    derived_df = _compute_derived(income_df, balance_df, cashflow_df)

    coverage = build_coverage_report(
        requested_tickers=request.tickers,
        income_df=income_df,
        balance_df=balance_df,
        cashflow_df=cashflow_df,
    )

    return SnapshotResult(
        cutoff=request.cutoff_date,
        tables={
            "company_master": company_df,
            "filings": filings_df,
            "statements_income": income_df,
            "statements_balance": balance_df,
            "statements_cashflow": cashflow_df,
            "derived_metrics": derived_df,
        },
        coverage_report=coverage,
    )


def _assemble_df(rows: list[dict], schema) -> pd.DataFrame:
    """Assemble a list of row dicts into a typed DataFrame."""
    if not rows:
        return schema.empty_dataframe()
    df = pd.DataFrame(rows)
    for col in schema.all_column_names:
        if col not in df.columns:
            df[col] = None
    return df[schema.all_column_names]


def _compute_derived(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cashflow: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute derived metrics by joining income, balance, and cashflow tables.

    Returns an empty DataFrame if inputs are missing.
    """
    if income.empty:
        return DERIVED_SCHEMA.empty_dataframe()

    df = income[["ticker", "cik", "accession", "asof_date", "period_end", "source",
                 "revenue", "ebit", "net_income"]].copy()

    # Cast to float64 early to avoid object-dtype issues
    for col in ["revenue", "ebit", "net_income"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Merge in balance data
    if not balance.empty:
        bal_cols = [c for c in ["cik", "period_end", "total_assets", "total_equity",
                                "total_liabilities", "long_term_debt", "short_term_debt",
                                "cash_and_equivalents"] if c in balance.columns]
        bal = balance[bal_cols].copy()
        for col in bal_cols[2:]:
            bal[col] = pd.to_numeric(bal[col], errors="coerce")
        df = df.merge(bal, on=["cik", "period_end"], how="left")

    # Merge in FCF
    if not cashflow.empty:
        cf_cols = [c for c in ["cik", "period_end", "cfo", "free_cash_flow"] if c in cashflow.columns]
        cf = cashflow[cf_cols].copy()
        df = df.merge(cf, on=["cik", "period_end"], how="left")

    # Helper: get Series as float64
    def _col(name: str) -> pd.Series | None:
        if name not in df.columns:
            return None
        return pd.to_numeric(df[name], errors="coerce")

    rev = _col("revenue")
    ebit = _col("ebit")
    ni = _col("net_income")
    assets = _col("total_assets")
    equity = _col("total_equity")
    ltd = _col("long_term_debt")
    stb = _col("short_term_debt")
    cash = _col("cash_and_equivalents")

    df["gross_margin"] = None
    df["ebit_margin"] = _safe_div(ebit, rev)
    df["net_margin"] = _safe_div(ni, rev)
    df["roa"] = _safe_div(ni, assets)
    df["roe"] = _safe_div(ni, equity)
    df["roic"] = None

    if ltd is not None and stb is not None and cash is not None:
        df["net_debt"] = ltd.fillna(0) + stb.fillna(0) - cash.fillna(0)
    elif ltd is not None:
        df["net_debt"] = ltd.fillna(0)
    else:
        df["net_debt"] = None

    df["debt_to_equity"] = _safe_div(ltd, equity) if ltd is not None else None
    df["current_ratio"] = None
    df["quick_ratio"] = None
    df["fcf_yield"] = None

    for col in DERIVED_SCHEMA.all_column_names:
        if col not in df.columns:
            df[col] = None

    return df[DERIVED_SCHEMA.all_column_names]


def _safe_div(
    numerator: pd.Series | None,
    denominator: pd.Series | None,
) -> pd.Series | None:
    """Return numerator / denominator, with NaN on zero or missing."""
    if numerator is None or denominator is None:
        return None
    with_denom = denominator.abs() > 0
    result = pd.Series(index=numerator.index, dtype="float64")
    result[with_denom] = numerator[with_denom] / denominator[with_denom]
    result[~with_denom] = None
    return result

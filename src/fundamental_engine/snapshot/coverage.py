"""
coverage.py – Generates a CoverageReport describing snapshot completeness.

Used to document which tickers had data, which didn't, and which
specific fields were unavailable for a given snapshot.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from fundamental_engine.data.schema import INCOME_SCHEMA
from fundamental_engine.types import CoverageReport

logger = logging.getLogger(__name__)

# Fields considered 'core' – their absence is worth highlighting
CORE_INCOME_FIELDS = ["revenue", "net_income", "ebit"]
CORE_BALANCE_FIELDS = ["total_assets", "total_liabilities", "total_equity"]
CORE_CASHFLOW_FIELDS = ["cfo", "capex"]


def build_coverage_report(
    requested_tickers: list[str],
    income_df: pd.DataFrame,
    balance_df: pd.DataFrame,
    cashflow_df: pd.DataFrame,
) -> CoverageReport:
    """
    Build a CoverageReport for a completed snapshot.

    Parameters
    ----------
    requested_tickers:
        Full list of tickers that were requested.
    income_df:
        Standardized income statement DataFrame.
    balance_df:
        Standardized balance sheet DataFrame.
    cashflow_df:
        Standardized cashflow DataFrame.

    Returns
    -------
    CoverageReport
    """
    # Determine which tickers appear in at least one table
    present: set[str] = set()
    for df in (income_df, balance_df, cashflow_df):
        if not df.empty and "ticker" in df.columns:
            present.update(df["ticker"].dropna().unique())

    found = [t for t in requested_tickers if t in present]
    missing = [t for t in requested_tickers if t not in present]

    # Count filings per ticker
    filing_counts: dict[str, int] = {}
    if not income_df.empty and "ticker" in income_df.columns:
        for ticker, grp in income_df.groupby("ticker"):
            filing_counts[str(ticker)] = len(grp)

    # Detect missing core fields per ticker
    missing_fields: dict[str, list[str]] = {}
    for ticker in found:
        absent: list[str] = []
        _check_fields(income_df, ticker, CORE_INCOME_FIELDS, absent)
        _check_fields(balance_df, ticker, CORE_BALANCE_FIELDS, absent)
        _check_fields(cashflow_df, ticker, CORE_CASHFLOW_FIELDS, absent)
        if absent:
            missing_fields[ticker] = absent

    report = CoverageReport(
        total_tickers=len(requested_tickers),
        found_tickers=found,
        missing_tickers=missing,
        missing_fields=missing_fields,
        filing_counts=filing_counts,
    )

    logger.info(
        "Coverage: %d/%d tickers found (%.1f%%)",
        len(found), len(requested_tickers), report.coverage_ratio * 100,
    )
    if missing:
        logger.warning("Missing tickers: %s", missing)

    return report


def _check_fields(
    df: pd.DataFrame,
    ticker: str,
    fields: list[str],
    absent: list[str],
) -> None:
    """Append to ``absent`` any fields that are entirely null for this ticker."""
    if df.empty or "ticker" not in df.columns:
        absent.extend(f"{f}(no_data)" for f in fields)
        return

    sub = df[df["ticker"] == ticker]
    if sub.empty:
        return

    for field in fields:
        if field in sub.columns and sub[field].isna().all():
            absent.append(field)

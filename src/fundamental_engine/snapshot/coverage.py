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
    Build a detailed CoverageReport for a completed snapshot.

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
    dict with detailed coverage metrics.
    """
    present: set[str] = set()
    dfs = {
        "income": income_df,
        "balance": balance_df,
        "cashflow": cashflow_df,
    }

    for df in dfs.values():
        if not df.empty and "ticker" in df.columns:
            present.update(df["ticker"].dropna().unique())

    found = [t for t in requested_tickers if t in present]
    missing = [t for t in requested_tickers if t not in present]

    filing_counts = {}
    if not income_df.empty and "ticker" in income_df.columns:
        for ticker, grp in income_df.groupby("ticker"):
            filing_counts[str(ticker)] = len(grp)

    # Detailed coverage metrics
    meta_cols = ["ticker", "cik", "accession", "asof_date", "period_end", "source"]
    
    statement_coverage = {}
    ticker_coverage = {t: {} for t in found}
    
    total_cells_all = 0
    total_filled_all = 0

    for stmt_name, df in dfs.items():
        if df.empty or "ticker" not in df.columns:
            statement_coverage[stmt_name] = {"rows": 0, "coverage_pct": 0.0, "missing_fields": []}
            for t in found:
                ticker_coverage[t][stmt_name] = {"rows": 0, "coverage_pct": 0.0, "missing_fields": ["ALL"]}
            continue

        data_cols = [c for c in df.columns if c not in meta_cols]
        total_rows = len(df)
        total_cells = total_rows * len(data_cols)
        total_filled = df[data_cols].notna().sum().sum()
        
        total_cells_all += total_cells
        total_filled_all += total_filled
        
        stmt_pct = (total_filled / total_cells * 100) if total_cells > 0 else 0.0
        
        # Statement level missing fields
        stmt_col_coverage = {col: (df[col].notna().sum() / total_rows * 100) if total_rows > 0 else 0 for col in data_cols}
        stmt_missing_fields = [k for k, v in stmt_col_coverage.items() if v == 0.0]
        
        statement_coverage[stmt_name] = {
            "rows": total_rows,
            "coverage_pct": round(stmt_pct, 1),
            "missing_fields": stmt_missing_fields
        }
        
        for ticker in found:
            ticker_df = df[df["ticker"] == ticker]
            t_rows = len(ticker_df)
            t_cells = t_rows * len(data_cols)
            t_filled = ticker_df[data_cols].notna().sum().sum()
            t_pct = (t_filled / t_cells * 100) if t_cells > 0 else 0.0
            
            t_col_coverage = {col: (ticker_df[col].notna().sum() / t_rows * 100) if t_rows > 0 else 0 for col in data_cols}
            t_missing_fields = [k for k, v in t_col_coverage.items() if v == 0.0]
            
            ticker_coverage[ticker][stmt_name] = {
                "rows": t_rows,
                "coverage_pct": round(t_pct, 1),
                "missing_fields": t_missing_fields
            }

    overall_pct = (total_filled_all / total_cells_all * 100) if total_cells_all > 0 else 0.0

    report = CoverageReport(
        total_tickers=len(requested_tickers),
        found_tickers=found,
        missing_tickers=missing,
        overall_coverage_pct=round(overall_pct, 1),
        statement_coverage=statement_coverage,
        ticker_coverage=ticker_coverage,
        filing_counts=filing_counts,
    )

    logger.info(
        "Coverage: %d/%d tickers found (%.1f%%)",
        len(found), len(requested_tickers), report.coverage_ratio * 100,
    )
    if missing:
        logger.warning("Missing tickers: %s", missing)

    return report

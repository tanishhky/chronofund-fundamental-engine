"""
ingest.py – Entry point for Bloomberg data ingestion.

Orchestrates reading Bloomberg source files (XLSX or PDF), parsing them
into RawStatementTable objects, and mapping to standardized DataFrames.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

import pandas as pd

from fundamental_engine.bloomberg.mapping import BloombergMapper
from fundamental_engine.bloomberg.parsers.xlsx_generic import XLSXGenericParser
from fundamental_engine.config import EngineConfig
from fundamental_engine.data.schema import (
    BALANCE_SCHEMA,
    CASHFLOW_SCHEMA,
    INCOME_SCHEMA,
)
from fundamental_engine.exceptions import BloombergParseError
from fundamental_engine.types import DataSource, SnapshotResult, CoverageReport

logger = logging.getLogger(__name__)


def build_bloomberg_snapshot_from_xlsx(
    path: Path,
    cutoff_date: datetime.date,
    ticker: str,
    config: EngineConfig | None = None,
) -> SnapshotResult:
    """
    Build a SnapshotResult from a Bloomberg XLSX export.

    Parameters
    ----------
    path:
        Path to the Bloomberg XLSX file.
    cutoff_date:
        Point-in-time cutoff. Columns added after this date are excluded.
    ticker:
        Equity ticker to associate with the data.
    config:
        Optional engine config (for estimate/LTM settings).

    Returns
    -------
    SnapshotResult
    """
    cfg = config or EngineConfig()
    parser = XLSXGenericParser(
        allow_ltm=cfg.allow_ltm,
        allow_estimates=cfg.allow_estimates,
    )

    try:
        raw_tables = parser.parse(path, ticker=ticker, cutoff_date=cutoff_date)
    except Exception as exc:
        raise BloombergParseError(str(path), str(exc)) from exc

    mapper = BloombergMapper()

    income_rows: list[dict] = []
    balance_rows: list[dict] = []
    cashflow_rows: list[dict] = []

    for raw in raw_tables:
        rows = mapper.map_to_rows(raw, cutoff_date=cutoff_date)
        for row in rows:
            st = row.get("_statement_type")
            if st == "income":
                income_rows.append(row)
            elif st == "balance":
                balance_rows.append(row)
            elif st == "cashflow":
                cashflow_rows.append(row)

    def _to_df(rows: list[dict], schema) -> pd.DataFrame:
        if not rows:
            return schema.empty_dataframe()
        df = pd.DataFrame(rows)
        # Drop internal marker column
        df = df.drop(columns=["_statement_type"], errors="ignore")
        # Ensure all schema columns present
        for col in schema.all_column_names:
            if col not in df.columns:
                df[col] = None
        return df[schema.all_column_names]

    income_df = _to_df(income_rows, INCOME_SCHEMA)
    balance_df = _to_df(balance_rows, BALANCE_SCHEMA)
    cashflow_df = _to_df(cashflow_rows, CASHFLOW_SCHEMA)

    found = [ticker] if (not income_df.empty or not balance_df.empty) else []
    coverage = CoverageReport(
        total_tickers=1,
        found_tickers=found,
        missing_tickers=[] if found else [ticker],
        filing_counts={ticker: len(income_df)} if found else {},
    )

    return SnapshotResult(
        cutoff=cutoff_date,
        tables={
            "statements_income": income_df,
            "statements_balance": balance_df,
            "statements_cashflow": cashflow_df,
        },
        coverage_report=coverage,
    )

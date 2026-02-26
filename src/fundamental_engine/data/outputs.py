"""
outputs.py – Assembles and writes SnapshotResult tables to disk.

Handles format selection, directory creation, and optional validation
before writing.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path

import pandas as pd

from fundamental_engine.data.validation import assert_valid_table
from fundamental_engine.types import CoverageReport, SnapshotResult
from fundamental_engine.utils.io import write_dataframe

logger = logging.getLogger(__name__)


def write_snapshot(
    result: SnapshotResult,
    output_dir: Path,
    fmt: str = "parquet",
    validate: bool = True,
) -> dict[str, Path]:
    """
    Write all tables in a SnapshotResult to disk.

    Parameters
    ----------
    result:
        The snapshot to persist.
    output_dir:
        Root output directory. Each snapshot will be written under
        ``{output_dir}/{cutoff_date}/``.
    fmt:
        'parquet' or 'csv'.
    validate:
        If True, run schema validation before writing.

    Returns
    -------
    dict mapping table_name → written file path.
    """
    dated_dir = output_dir / str(result.cutoff)
    dated_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}

    for table_name, df in result.tables.items():
        if df is None or df.empty:
            logger.warning("Table '%s' is empty—skipping write.", table_name)
            continue

        if validate:
            try:
                assert_valid_table(df, table_name)
            except Exception as exc:
                logger.warning("Validation warning for '%s': %s", table_name, exc)

        path = write_dataframe(df, dated_dir, table_name, fmt=fmt)
        written[table_name] = path
        logger.info("Wrote table '%s': %d rows → %s", table_name, len(df), path)

    # Write coverage report
    _write_coverage_report(result.coverage_report, result.cutoff, dated_dir)

    return written


def _write_coverage_report(
    report: CoverageReport,
    cutoff: datetime.date,
    out_dir: Path,
) -> None:
    """Write the coverage report as a JSON file."""
    data = {
        "cutoff": str(cutoff),
        "total_tickers": report.total_tickers,
        "found_tickers": report.found_tickers,
        "missing_tickers": report.missing_tickers,
        "coverage_ratio": round(report.coverage_ratio, 4),
        "overall_coverage_pct": report.overall_coverage_pct,
        "filing_counts": report.filing_counts,
        "statement_coverage": report.statement_coverage,
        "ticker_coverage": report.ticker_coverage,
    }
    path = out_dir / "coverage_report.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
    logger.info("Coverage report written → %s", path)

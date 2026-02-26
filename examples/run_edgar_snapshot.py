"""
run_edgar_snapshot.py – Example: Pull a point-in-time EDGAR snapshot.

Usage:
  python examples/run_edgar_snapshot.py

Note: Requires SEC_USER_AGENT to be set in environment or .env file.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from fundamental_engine.config import EngineConfig
from fundamental_engine.data.outputs import write_snapshot
from fundamental_engine.snapshot.builder import build_edgar_snapshot
from fundamental_engine.types import FilingPeriodType, SnapshotRequest
from fundamental_engine.utils.logging import configure_logging

# ── Configuration ─────────────────────────────────────────────────────────────
TICKERS = ["AAPL", "MSFT", "GOOGL"]
CUTOFF_DATE = datetime.date(2016, 12, 31)   # <-- Point-in-time cutoff
OUTPUT_DIR = Path("out/edgar_example")
FORMAT = "parquet"  # or "csv"

configure_logging("INFO")


def main() -> None:
    # Build engine config — reads SEC_USER_AGENT from .env or environment
    config = EngineConfig(
        user_agent="ResearchProject/1.0 researcher@example.com",
        cache_dir=Path(".cache"),
        allow_amendments=True,
        allow_ltm=False,      # Strict PIT — no LTM columns
        allow_estimates=False,  # MUST be False for backtests
    )

    # Define what we want to pull
    request = SnapshotRequest(
        tickers=TICKERS,
        cutoff_date=CUTOFF_DATE,
        period_type=FilingPeriodType.ANNUAL,
        allow_estimates=False,
        allow_ltm=False,
    )

    print(f"\n📊 Pulling EDGAR snapshot as of {CUTOFF_DATE}...")
    print(f"   Tickers: {TICKERS}")
    print(f"   No data filed after {CUTOFF_DATE} will be included.\n")

    result = build_edgar_snapshot(request, config=config)

    # Print coverage summary
    report = result.coverage_report
    print(f"\n✅ Coverage: {len(report.found_tickers)}/{report.total_tickers} tickers")
    if report.missing_tickers:
        print(f"   ⚠️  Missing: {report.missing_tickers}")

    # Show sample of income data
    income = result.tables.get("statements_income")
    if income is not None and not income.empty:
        print("\nIncome Statement (sample):")
        print(income[["ticker", "period_end", "revenue", "net_income"]].head())

    # Persist to disk
    written = write_snapshot(result, OUTPUT_DIR, fmt=FORMAT, validate=True)
    print(f"\n💾 Snapshot written to: {OUTPUT_DIR}/{CUTOFF_DATE}/")
    for table, path in written.items():
        print(f"   {table}: {path.name}")


if __name__ == "__main__":
    main()

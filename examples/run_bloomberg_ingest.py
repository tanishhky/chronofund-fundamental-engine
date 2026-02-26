"""
run_bloomberg_ingest.py – Example: Ingest a Bloomberg XLSX financial statement export.

Usage:
  python examples/run_bloomberg_ingest.py --file path/to/bloomberg.xlsx

The Bloomberg XLSX file should have sheets named:
  - "Income" / "Income Statement" / "P&L"
  - "Balance" / "Balance Sheet"
  - "Cash" / "CashFlow" / "CF"

Column headers should include fiscal year labels like "2021A", "2022A", "2022E".
The parser will automatically:
  - Detect "In Millions" scale
  - Exclude estimate (E, Est, Proj) columns
  - Exclude LTM/TTM columns
  - Exclude columns with period_end > cutoff_date
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

from fundamental_engine.bloomberg.ingest import build_bloomberg_snapshot_from_xlsx
from fundamental_engine.config import EngineConfig
from fundamental_engine.data.outputs import write_snapshot
from fundamental_engine.utils.logging import configure_logging

configure_logging("INFO")

# ── Configuration ─────────────────────────────────────────────────────────────
CUTOFF_DATE = datetime.date(2016, 12, 31)
OUTPUT_DIR = Path("out/bloomberg_example")
TICKER = "AAPL"


def main(xlsx_path: Path) -> None:
    config = EngineConfig(
        user_agent="ResearchProject/1.0 researcher@example.com",
        allow_ltm=False,
        allow_estimates=False,
    )

    print(f"\n📊 Ingesting Bloomberg XLSX: {xlsx_path}")
    print(f"   Ticker: {TICKER} | Cutoff: {CUTOFF_DATE}")
    print(f"   Estimates: EXCLUDED | LTM: EXCLUDED\n")

    result = build_bloomberg_snapshot_from_xlsx(
        path=xlsx_path,
        cutoff_date=CUTOFF_DATE,
        ticker=TICKER,
        config=config,
    )

    report = result.coverage_report
    print(f"✅ Coverage: {len(report.found_tickers)}/{report.total_tickers} tickers")

    income = result.tables.get("statements_income")
    if income is not None and not income.empty:
        print(f"\nIncome Statement ({len(income)} period rows):")
        cols = [c for c in ("ticker", "period_end", "revenue", "net_income") if c in income.columns]
        print(income[cols].to_string(index=False))

    written = write_snapshot(result, OUTPUT_DIR, fmt="parquet", validate=True)
    print(f"\n💾 Output: {OUTPUT_DIR}/{CUTOFF_DATE}/")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Run with a dummy path for demonstration
        print("Usage: python run_bloomberg_ingest.py path/to/bloomberg.xlsx")
        print("No file provided. Please pass an XLSX path as argument.")
        sys.exit(0)

    main(Path(sys.argv[1]))

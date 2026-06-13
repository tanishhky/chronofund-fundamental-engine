"""
verify_pit_gating.py - Live, end-to-end proof of point-in-time correctness.

Pulls Apple's annual fundamentals at two cutoffs that straddle its FY2016 10-K
(accepted 2016-10-26) and prints the latest annual period available at each.

Expected (no-lookahead enforced):
  as-of 2016-06-01  ->  FY2015 (period_end 2015-09-26)   # FY2016 10-K not yet filed
  as-of 2017-06-01  ->  FY2016 (period_end 2016-09-24)   # now available

If the FY2016 figures appear under the 2016-06-01 cutoff, the gate has leaked.

Run:  python examples/verify_pit_gating.py
Requires a descriptive SEC user-agent (set below or via SEC_USER_AGENT).
"""
from __future__ import annotations

import datetime
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from fundamental_engine.config import EngineConfig
from fundamental_engine.snapshot.builder import build_edgar_snapshot
from fundamental_engine.types import FilingPeriodType, SnapshotRequest

CONFIG = EngineConfig(
    user_agent="ChronoFund Research example@example.com",
    cache_dir=Path(".cache"),
    allow_amendments=True,
    allow_ltm=False,
    allow_estimates=False,
)


def latest_annual(ticker: str, cutoff: datetime.date):
    request = SnapshotRequest(
        tickers=[ticker],
        cutoff_date=cutoff,
        period_type=FilingPeriodType.ANNUAL,
        allow_estimates=False,
        allow_ltm=False,
    )
    result = build_edgar_snapshot(request, config=CONFIG)
    income = result.tables.get("statements_income")
    if income is None or income.empty:
        return None
    return income.sort_values("period_end").iloc[-1]


def main() -> None:
    for cutoff in (datetime.date(2016, 6, 1), datetime.date(2017, 6, 1)):
        row = latest_annual("AAPL", cutoff)
        if row is None:
            print(f"as-of {cutoff}: no data")
            continue
        print(
            f"as-of {cutoff}: latest annual period_end={row['period_end']} "
            f"revenue={row.get('revenue')}"
        )


if __name__ == "__main__":
    main()

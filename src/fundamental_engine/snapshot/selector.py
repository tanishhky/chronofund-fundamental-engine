"""
selector.py – Selects the best filing(s) per period for a ticker.

Implements the filing selection logic used by the snapshot builder:
- One row per fiscal period (period_end)
- Prefer amendments (10-K/A) over originals when config allows
- Respect the PIT cutoff (already enforced upstream by FilingsIndex,
  but asserted here as a safety check)
"""

from __future__ import annotations

import datetime
import logging
from collections import defaultdict

from fundamental_engine.config import EngineConfig
from fundamental_engine.exceptions import CutoffViolationError
from fundamental_engine.types import FilingRecord

logger = logging.getLogger(__name__)

_AMENDMENT_SUFFIX = "/A"


class FilingSelector:
    """
    Given a list of FilingRecords (already PIT-filtered), selects one
    filing per fiscal period.

    Parameters
    ----------
    config:
        Engine configuration providing the default allow_amendments setting.
    allow_amendments:
        If provided, overrides config.allow_amendments. Use this to pass in
        the value from ResolvedConfig to enforce SnapshotRequest precedence.
    """

    def __init__(self, config: EngineConfig, allow_amendments: bool | None = None) -> None:
        self._config = config
        # ResolvedConfig value takes precedence; fall back to engine config default
        self._allow_amendments = (
            allow_amendments if allow_amendments is not None else config.allow_amendments
        )

    def select(
        self,
        filings: list[FilingRecord],
        cutoff_date: datetime.date,
    ) -> list[FilingRecord]:
        """
        Select the single best filing per period_of_report.

        Parameters
        ----------
        filings:
            Pre-PIT-filtered list of FilingRecords.
        cutoff_date:
            Used for a secondary safety assertion; raises CutoffViolationError
            if any filing slips through with an acceptance_datetime after cutoff.

        Returns
        -------
        list[FilingRecord] – one record per unique period_of_report, sorted by
        period descending.
        """
        # Safety assertion: should never fail (upstream gate in filings_index)
        for rec in filings:
            cutoff_end = datetime.datetime.combine(cutoff_date, datetime.time(23, 59, 59))
            if rec.acceptance_datetime > cutoff_end:
                raise CutoffViolationError(
                    ticker=rec.ticker or rec.cik,  # ticker is preferred; fall back to CIK
                    cutoff_date=cutoff_date,
                    acceptance_datetime=rec.acceptance_datetime,
                    accession=rec.accession,
                )

        # Group by period_of_report
        by_period: dict[datetime.date, list[FilingRecord]] = defaultdict(list)
        for rec in filings:
            by_period[rec.period_of_report].append(rec)

        selected: list[FilingRecord] = []
        for period_end, candidates in by_period.items():
            chosen = self._pick_best(candidates)
            selected.append(chosen)

        selected.sort(key=lambda r: r.period_of_report, reverse=True)
        return selected

    def _pick_best(self, candidates: list[FilingRecord]) -> FilingRecord:
        """
        Among candidate filings for the same period, pick the best one.

        Priority:
        1. Amendment (10-K/A, 10-Q/A) if allow_amendments is True
        2. Most recently filed (latest acceptance_datetime)
        """
        if self._allow_amendments:
            amendments = [c for c in candidates if c.form_type.endswith(_AMENDMENT_SUFFIX)]
            if amendments:
                candidates = amendments

        return max(candidates, key=lambda r: r.acceptance_datetime)

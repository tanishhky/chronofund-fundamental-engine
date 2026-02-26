"""
contexts.py – XBRL context selection utilities.

XBRL facts can have many contexts (time periods, entity segments).
This module implements the logic for selecting the "best" context for
each standardized field, preferring:
  1. Consolidated entity (no explicit segment)
  2. Correct period duration (annual ~330–400d, quarterly ~80–100d)
  3. Most recently filed fact per period

Key design decisions
--------------------
- `frame` is treated as a PREFERENCE signal, never a hard filter.
  SEC's companyfacts API only assigns frame labels to facts that fall on
  calendar-year boundaries (e.g., "CY2016Q3"). Companies with non-calendar
  fiscal years (AAPL ends Sept, MSFT ends June) typically have NO frame on
  their annual totals, so hard-filtering on frame drops all their data.

- Period-end matching uses a ±7-day tolerance as a fallback.
  52/53-week fiscal years, leap years, and XBRL reporting conventions mean
  the SEC-reported period_end can differ by a few days from what the filing
  index records as period_of_report. The primary match is still exact
  (f.end == period_end); the fuzzy match is only used when nothing exact is
  found.
"""

from __future__ import annotations

import datetime
import logging
from typing import Sequence

from fundamental_engine.types import XBRLContextType, XBRLFact
from fundamental_engine.utils.dates import is_annual_period, is_quarterly_period

logger = logging.getLogger(__name__)

# Tolerance in days for fuzzy period-end matching (covers 52/53-week year drift)
_PERIOD_END_TOLERANCE_DAYS = 7


def filter_facts_by_period_type(
    facts: list[XBRLFact],
    context_type: XBRLContextType,
    annual: bool = True,
) -> list[XBRLFact]:
    """
    Filter XBRL facts to those matching the desired period type.

    Parameters
    ----------
    facts:
        All facts for a given XBRL tag.
    context_type:
        DURATION or INSTANT. Income/cashflow facts are DURATION; balance
        sheet facts are INSTANT.
    annual:
        If True, only include annual (330–400 day) duration periods.
        If False, include quarterly (~80–100 day) periods.

    Returns
    -------
    Filtered list of XBRLFact.
    """
    result: list[XBRLFact] = []
    for fact in facts:
        if context_type == XBRLContextType.INSTANT:
            if fact.start is None:
                result.append(fact)
        elif context_type == XBRLContextType.DURATION:
            if fact.start is not None:
                if annual and is_annual_period(fact.start, fact.end):
                    result.append(fact)
                elif not annual and is_quarterly_period(fact.start, fact.end):
                    result.append(fact)
    return result


def prefer_consolidated(facts: list[XBRLFact]) -> list[XBRLFact]:
    """
    Prefer facts without segment specifiers (i.e., consolidated entity).

    ``frame`` is used as a PREFERENCE signal only — facts with a frame label
    are returned if any exist. If none have frame labels (common for non-
    calendar fiscal years), the full original list is returned unchanged so
    that callers can still select the best fact.

    Parameters
    ----------
    facts:
        List of facts to filter.

    Returns
    -------
    Facts with frame set if any exist; otherwise the original list.
    """
    with_frame = [f for f in facts if f.frame]
    return with_frame if with_frame else facts


def select_best_fact_for_period(
    facts: list[XBRLFact],
    period_end: datetime.date,
    cutoff_date: datetime.date,
) -> XBRLFact | None:
    """
    Select the best XBRL fact for a specific period end date.

    Prioritization:
    1. Exact match: f.end == period_end, filed <= cutoff_date
    2. Prefer consolidated (frame) within the exact match set
    3. Fuzzy fallback: |f.end - period_end| <= 7 days (for 52/53-week years)
    4. Among ties: most recently filed

    Parameters
    ----------
    facts:
        List of candidate facts with matching tag, already filtered by
        period type (annual/quarterly) and consolidated preference.
    period_end:
        The fiscal period end date we want data for.
    cutoff_date:
        Point-in-time cutoff; facts filed after this date are excluded.

    Returns
    -------
    The best XBRLFact or None if no suitable fact exists.
    """
    # Primary: facts actually filed within the PIT window
    eligible = [f for f in facts if f.filed <= cutoff_date]

    if not eligible:
        return None

    # Exact period_end match
    exact = [f for f in eligible if f.end == period_end]

    if exact:
        # Prefer consolidated (with frame) within exact matches
        framed = [f for f in exact if f.frame]
        pool = framed if framed else exact
        return max(pool, key=lambda f: f.filed)

    # Fuzzy fallback: ±7 days to handle 52/53-week fiscal years and XBRL drift
    tolerance = datetime.timedelta(days=_PERIOD_END_TOLERANCE_DAYS)
    fuzzy = [
        f for f in eligible
        if abs((f.end - period_end).days) <= _PERIOD_END_TOLERANCE_DAYS
    ]

    if fuzzy:
        # Among fuzzy matches, prefer the one whose end is closest to period_end,
        # then prefer consolidated (framed), then most recently filed
        best_distance = min(abs((f.end - period_end).days) for f in fuzzy)
        closest = [f for f in fuzzy if abs((f.end - period_end).days) == best_distance]
        framed = [f for f in closest if f.frame]
        pool = framed if framed else closest

        if logger.isEnabledFor(logging.DEBUG):
            chosen = max(pool, key=lambda f: f.filed)
            logger.debug(
                "Fuzzy period_end match: requested=%s found=%s diff=%dd",
                period_end, chosen.end, (chosen.end - period_end).days,
            )

        return max(pool, key=lambda f: f.filed)

    return None


def group_facts_by_period_end(
    facts: list[XBRLFact],
) -> dict[datetime.date, list[XBRLFact]]:
    """
    Group a flat list of facts by their period end date.

    Parameters
    ----------
    facts:
        Any list of XBRLFacts.

    Returns
    -------
    dict[datetime.date, list[XBRLFact]]
    """
    groups: dict[datetime.date, list[XBRLFact]] = {}
    for fact in facts:
        groups.setdefault(fact.end, []).append(fact)
    return groups

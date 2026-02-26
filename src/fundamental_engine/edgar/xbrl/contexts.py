"""
contexts.py – XBRL context selection utilities.

XBRL facts can have many contexts (time periods, entity segments).
This module implements the logic for selecting the "best" context for
each standardized field, preferring:
  1. Consolidated entity (no explicit segment)
  2. Correct period duration (annual ~365d, quarterly ~90d)
  3. Most recently filed fact per period
"""

from __future__ import annotations

import datetime
import logging
from typing import Sequence

from fundamental_engine.types import XBRLContextType, XBRLFact
from fundamental_engine.utils.dates import is_annual_period, is_quarterly_period

logger = logging.getLogger(__name__)


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
        If True, only include annual (365-day) duration periods.
        If False, include quarterly (~90d) periods.

    Returns
    -------
    Filtered list of XBRLFact.
    """
    result: list[XBRLFact] = []
    for fact in facts:
        if context_type == XBRLContextType.INSTANT:
            # Instant facts have no start date
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

    In EDGAR, consolidated facts often have a 'frame' without entity segment
    qualifiers. Facts with explicit segments (e.g., business units) are
    deprioritized. We use the presence of a frame label as a proxy for
    consolidated data.

    Parameters
    ----------
    facts:
        List of facts to filter.

    Returns
    -------
    Facts with frame set (consolidated), or original list if none have frames.
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
    1. Facts where end == period_end
    2. Facts filed most recently (but not after cutoff_date)
    3. Most recently filed fact among ties

    Parameters
    ----------
    facts:
        List of candidate facts with matching tag.
    period_end:
        The fiscal period end date we want data for.
    cutoff_date:
        Point-in-time cutoff; facts filed after this date are excluded.

    Returns
    -------
    The best XBRLFact or None if no suitable fact exists.
    """
    # Only consider facts with matching period end and filed ≤ cutoff
    candidates = [
        f for f in facts
        if f.end == period_end and f.filed <= cutoff_date
    ]

    if not candidates:
        return None

    # Prefer consolidated (with frame)
    framed = [f for f in candidates if f.frame]
    pool = framed if framed else candidates

    # Among pool, pick most recently filed
    return max(pool, key=lambda f: f.filed)


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

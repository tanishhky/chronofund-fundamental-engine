"""
dates.py – Point-in-time date utilities.

Core principle: ALL cutoff comparisons must flow through this module.
Never compare dates directly in business logic—use these helpers.
"""

from __future__ import annotations

import datetime
from typing import Sequence


def parse_date(value: str | datetime.date | datetime.datetime | None) -> datetime.date | None:
    """
    Parse various date representations to a ``datetime.date``.

    Handles:
    - ISO strings: '2023-12-31'
    - Datetime objects (extracts date part)
    - None (returns None)

    Parameters
    ----------
    value:
        Input to parse.

    Returns
    -------
    datetime.date or None
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y"):
            try:
                return datetime.datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date string: {value!r}")
    raise TypeError(f"Unsupported date type: {type(value)}")


def parse_datetime(value: str | datetime.datetime | None) -> datetime.datetime | None:
    """
    Parse various datetime representations to UTC-naive ``datetime.datetime``.

    Handles:
    - ISO 8601 strings (with or without timezone)
    - Datetime objects (strips tzinfo)
    - None (returns None)

    Parameters
    ----------
    value:
        Input to parse.

    Returns
    -------
    datetime.datetime or None
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        value = value.strip().rstrip("Z")
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",   # SEC acceptanceDateTime: 2025-10-31T10:01:26.000
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y%m%d%H%M%S",            # SEC compact: 20251031100126
            "%Y-%m-%d",
        ):
            try:
                return datetime.datetime.strptime(value, fmt)
            except ValueError:
                continue
        raise ValueError(f"Cannot parse datetime string: {value!r}")
    raise TypeError(f"Unsupported datetime type: {type(value)}")


def is_within_cutoff(
    acceptance_datetime: datetime.datetime,
    cutoff_date: datetime.date,
) -> bool:
    """
    Return True if ``acceptance_datetime`` (naive, UTC equivalent) is
    **on or before the end of** ``cutoff_date``.

    This is the central point-in-time gate. No data with an acceptance
    datetime after cutoff may be used.

    Parameters
    ----------
    acceptance_datetime:
        When the filing was accepted by SEC (UTC-naive).
    cutoff_date:
        The investor's knowledge cutoff.

    Returns
    -------
    bool
    """
    # We compare against the very end of the cutoff day (23:59:59)
    cutoff_end = datetime.datetime.combine(cutoff_date, datetime.time(23, 59, 59))
    return acceptance_datetime <= cutoff_end


def fiscal_quarter(period_end: datetime.date) -> int:
    """Return the fiscal quarter (1-4) for a given period end date."""
    month = period_end.month
    if month in (1, 2, 3):
        return 1
    elif month in (4, 5, 6):
        return 2
    elif month in (7, 8, 9):
        return 3
    else:
        return 4


def period_duration_days(start: datetime.date, end: datetime.date) -> int:
    """Return the number of calendar days in a period."""
    return (end - start).days


def is_annual_period(start: datetime.date | None, end: datetime.date) -> bool:
    """
    Heuristic: consider a period annual if it spans ~330–400 days.

    Parameters
    ----------
    start:
        Period start date. If None, returns False.
    end:
        Period end date.
    """
    if start is None:
        return False
    days = period_duration_days(start, end)
    return 330 <= days <= 400


def is_quarterly_period(start: datetime.date | None, end: datetime.date) -> bool:
    """
    Heuristic: consider a period quarterly if it spans ~75–100 days.

    Parameters
    ----------
    start:
        Period start date. If None, returns False.
    end:
        Period end date.
    """
    if start is None:
        return False
    days = period_duration_days(start, end)
    return 75 <= days <= 100


def latest_date_within_cutoff(
    dates: Sequence[datetime.date],
    cutoff: datetime.date,
) -> datetime.date | None:
    """
    Return the most recent date from ``dates`` that is ≤ ``cutoff``.

    Parameters
    ----------
    dates:
        Sequence of dates to filter.
    cutoff:
        Upper boundary (inclusive).

    Returns
    -------
    datetime.date or None if no date qualifies.
    """
    eligible = [d for d in dates if d <= cutoff]
    return max(eligible) if eligible else None

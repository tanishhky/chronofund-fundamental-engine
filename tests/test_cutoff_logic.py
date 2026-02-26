"""
test_cutoff_logic.py – Unit tests for point-in-time cutoff enforcement.

Tests the core PIT safety functions in utils/dates.py and the
FilingSelector's secondary safety assertion.
"""

from __future__ import annotations

import datetime

import pytest

from fundamental_engine.config import EngineConfig
from fundamental_engine.exceptions import CutoffViolationError
from fundamental_engine.snapshot.selector import FilingSelector
from fundamental_engine.types import FilingRecord
from fundamental_engine.utils.dates import (
    is_annual_period,
    is_quarterly_period,
    is_within_cutoff,
    latest_date_within_cutoff,
    parse_date,
    parse_datetime,
)


class TestIsWithinCutoff:
    """Tests for the primary PIT gate function."""

    def test_same_day_is_within(self) -> None:
        cutoff = datetime.date(2016, 12, 31)
        acceptance = datetime.datetime(2016, 12, 31, 12, 0, 0)
        assert is_within_cutoff(acceptance, cutoff) is True

    def test_end_of_day_is_within(self) -> None:
        cutoff = datetime.date(2016, 12, 31)
        acceptance = datetime.datetime(2016, 12, 31, 23, 59, 59)
        assert is_within_cutoff(acceptance, cutoff) is True

    def test_one_second_over_cutoff(self) -> None:
        """Midnight of the NEXT day should be rejected."""
        cutoff = datetime.date(2016, 12, 31)
        acceptance = datetime.datetime(2017, 1, 1, 0, 0, 0)
        assert is_within_cutoff(acceptance, cutoff) is False

    def test_one_year_after_cutoff(self) -> None:
        cutoff = datetime.date(2016, 12, 31)
        acceptance = datetime.datetime(2017, 12, 31, 12, 0, 0)
        assert is_within_cutoff(acceptance, cutoff) is False

    def test_historical_filing_accepted(self) -> None:
        cutoff = datetime.date(2016, 12, 31)
        acceptance = datetime.datetime(2014, 3, 15, 9, 30, 0)
        assert is_within_cutoff(acceptance, cutoff) is True


class TestParseFunctions:
    """Tests for date/datetime parsing utilities."""

    def test_parse_date_iso(self) -> None:
        result = parse_date("2023-12-31")
        assert result == datetime.date(2023, 12, 31)

    def test_parse_date_compact(self) -> None:
        result = parse_date("20231231")
        assert result == datetime.date(2023, 12, 31)

    def test_parse_date_from_datetime(self) -> None:
        dt = datetime.datetime(2023, 6, 15, 10, 30, 0)
        assert parse_date(dt) == datetime.date(2023, 6, 15)

    def test_parse_date_none(self) -> None:
        assert parse_date(None) is None

    def test_parse_datetime_strips_tz(self) -> None:
        result = parse_datetime("2023-12-31T15:30:00Z")
        assert result == datetime.datetime(2023, 12, 31, 15, 30, 0)
        assert result.tzinfo is None

    def test_parse_date_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_date("not-a-date")


class TestPeriodHeuristics:
    """Tests for annual/quarterly period detection heuristics."""

    def test_is_annual_365_days(self) -> None:
        start = datetime.date(2022, 1, 1)
        end = datetime.date(2022, 12, 31)
        assert is_annual_period(start, end) is True

    def test_is_annual_366_days_leap_year(self) -> None:
        start = datetime.date(2024, 1, 1)
        end = datetime.date(2024, 12, 31)
        assert is_annual_period(start, end) is True  # 366 days

    def test_is_not_annual_quarterly(self) -> None:
        start = datetime.date(2022, 1, 1)
        end = datetime.date(2022, 3, 31)
        assert is_annual_period(start, end) is False

    def test_is_quarterly(self) -> None:
        start = datetime.date(2022, 7, 1)
        end = datetime.date(2022, 9, 30)
        assert is_quarterly_period(start, end) is True

    def test_is_not_quarterly_annual(self) -> None:
        start = datetime.date(2022, 1, 1)
        end = datetime.date(2022, 12, 31)
        assert is_quarterly_period(start, end) is False


class TestLatestDateWithinCutoff:
    """Tests for selecting the most recent date within cutoff."""

    def test_returns_latest_eligible(self) -> None:
        dates = [
            datetime.date(2015, 12, 31),
            datetime.date(2016, 12, 31),
            datetime.date(2017, 12, 31),  # after cutoff
        ]
        cutoff = datetime.date(2016, 12, 31)
        result = latest_date_within_cutoff(dates, cutoff)
        assert result == datetime.date(2016, 12, 31)

    def test_returns_none_when_all_after_cutoff(self) -> None:
        dates = [datetime.date(2020, 12, 31), datetime.date(2021, 12, 31)]
        cutoff = datetime.date(2016, 12, 31)
        assert latest_date_within_cutoff(dates, cutoff) is None

    def test_empty_list(self) -> None:
        assert latest_date_within_cutoff([], datetime.date(2016, 12, 31)) is None


class TestFilingSelector:
    """Tests for FilingSelector's safety assertion."""

    def _make_filing(
        self,
        period_end: datetime.date,
        acceptance: datetime.datetime,
        form: str = "10-K",
    ) -> FilingRecord:
        return FilingRecord(
            cik="0000320193",
            accession="0000320193-22-000100",
            form_type=form,
            filing_date=acceptance.date(),
            acceptance_datetime=acceptance,
            period_of_report=period_end,
        )

    def test_selector_raises_cutoff_violation(self) -> None:
        config = EngineConfig(user_agent="Test/1.0 test@test.com")
        selector = FilingSelector(config)
        cutoff = datetime.date(2016, 12, 31)

        # Filing accepted AFTER cutoff – should raise CutoffViolationError
        bad_filing = self._make_filing(
            period_end=datetime.date(2016, 12, 31),
            acceptance=datetime.datetime(2017, 2, 28, 12, 0, 0),
        )
        with pytest.raises(CutoffViolationError):
            selector.select([bad_filing], cutoff)

    def test_selector_prefers_amendment(self) -> None:
        config = EngineConfig(user_agent="Test/1.0 test@test.com", allow_amendments=True)
        selector = FilingSelector(config)
        cutoff = datetime.date(2016, 12, 31)

        original = self._make_filing(
            datetime.date(2015, 12, 31),
            datetime.datetime(2016, 2, 1, 12, 0, 0),
            "10-K",
        )
        amendment = self._make_filing(
            datetime.date(2015, 12, 31),
            datetime.datetime(2016, 3, 1, 12, 0, 0),
            "10-K/A",
        )

        selected = selector.select([original, amendment], cutoff)
        assert len(selected) == 1
        assert selected[0].form_type == "10-K/A"

    def test_selector_deduplicates_periods(self) -> None:
        config = EngineConfig(user_agent="Test/1.0 test@test.com", allow_amendments=False)
        selector = FilingSelector(config)
        cutoff = datetime.date(2016, 12, 31)

        f1 = self._make_filing(
            datetime.date(2015, 12, 31), datetime.datetime(2016, 2, 1)
        )
        f2 = self._make_filing(
            datetime.date(2015, 12, 31), datetime.datetime(2016, 3, 1)
        )  # Same period, later filing

        selected = selector.select([f1, f2], cutoff)
        assert len(selected) == 1
        assert selected[0].acceptance_datetime == datetime.datetime(2016, 3, 1)

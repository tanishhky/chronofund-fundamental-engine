"""
test_xbrl_mapping.py – Tests for XBRL tag → standard field mapping.

Tests the mapper module's priority map, reverse index, and the
XBRLParser's context selection logic.
"""

from __future__ import annotations

import datetime

import pytest

from fundamental_engine.edgar.xbrl.contexts import (
    filter_facts_by_period_type,
    prefer_consolidated,
    select_best_fact_for_period,
)
from fundamental_engine.edgar.xbrl.mapper import (
    FIELD_TO_MAPPING,
    TAG_PRIORITY_MAP,
    TAG_TO_FIELD,
)
from fundamental_engine.types import XBRLContextType, XBRLFact


def _make_fact(
    tag: str = "Revenues",
    namespace: str = "us-gaap",
    value: float = 1_000_000.0,
    start: datetime.date | None = None,
    end: datetime.date = datetime.date(2022, 12, 31),
    filed: datetime.date = datetime.date(2023, 2, 15),
    frame: str | None = "CY2022",
) -> XBRLFact:
    return XBRLFact(
        tag=tag,
        namespace=namespace,
        value=value,
        unit="USD",
        start=start,
        end=end,
        accession="0001234567-23-000001",
        form="10-K",
        frame=frame,
        filed=filed,
    )


class TestTagPriorityMap:
    """Tests for the static GAAP tag mapping table."""

    def test_revenue_field_exists(self) -> None:
        assert "revenue" in FIELD_TO_MAPPING

    def test_revenue_has_priority_tags(self) -> None:
        mapping = FIELD_TO_MAPPING["revenue"]
        assert len(mapping.tags) >= 3
        # The SEC standard Revenues tag should be the first priority
        assert "us-gaap:Revenues" in mapping.tags

    def test_capex_sign_flip(self) -> None:
        """CapEx is reported negative in filings; we should store it positive."""
        mapping = FIELD_TO_MAPPING["capex"]
        assert mapping.sign_flip is True

    def test_dividends_sign_flip(self) -> None:
        mapping = FIELD_TO_MAPPING["dividends_paid"]
        assert mapping.sign_flip is True

    def test_revenue_no_sign_flip(self) -> None:
        mapping = FIELD_TO_MAPPING["revenue"]
        assert mapping.sign_flip is False

    def test_balance_sheet_fields_are_instant(self) -> None:
        instant_fields = {"total_assets", "cash_and_equivalents", "total_equity", "goodwill"}
        for field in instant_fields:
            assert FIELD_TO_MAPPING[field].context_type == "instant", \
                f"Expected {field} to be instant context"

    def test_income_fields_are_duration(self) -> None:
        duration_fields = {"revenue", "net_income", "ebit", "cfo"}
        for field in duration_fields:
            assert FIELD_TO_MAPPING[field].context_type == "duration", \
                f"Expected {field} to be duration context"

    def test_reverse_index_populated(self) -> None:
        assert "us-gaap:Revenues" in TAG_TO_FIELD
        field_name, sign_flip, ctx = TAG_TO_FIELD["us-gaap:Revenues"]
        assert field_name == "revenue"
        assert sign_flip is False
        assert ctx == "duration"


class TestContextSelection:
    """Tests for XBRL context selection logic."""

    def test_filter_instant_facts(self) -> None:
        instant = _make_fact(start=None, end=datetime.date(2022, 12, 31))
        duration = _make_fact(
            start=datetime.date(2022, 1, 1), end=datetime.date(2022, 12, 31)
        )
        result = filter_facts_by_period_type(
            [instant, duration], XBRLContextType.INSTANT
        )
        assert instant in result
        assert duration not in result

    def test_filter_annual_duration_facts(self) -> None:
        annual = _make_fact(
            start=datetime.date(2022, 1, 1), end=datetime.date(2022, 12, 31)
        )
        quarterly = _make_fact(
            start=datetime.date(2022, 10, 1), end=datetime.date(2022, 12, 31)
        )
        result = filter_facts_by_period_type(
            [annual, quarterly], XBRLContextType.DURATION, annual=True
        )
        assert annual in result
        assert quarterly not in result

    def test_prefer_consolidated_with_frame(self) -> None:
        with_frame = _make_fact(frame="CY2022")
        without_frame = _make_fact(frame=None)
        result = prefer_consolidated([with_frame, without_frame])
        assert with_frame in result
        assert without_frame not in result

    def test_prefer_consolidated_fallback_to_all(self) -> None:
        without_frame1 = _make_fact(frame=None)
        without_frame2 = _make_fact(frame=None, value=999)
        result = prefer_consolidated([without_frame1, without_frame2])
        # Should return both when none have frames
        assert len(result) == 2

    def test_select_best_fact_for_period(self) -> None:
        period = datetime.date(2022, 12, 31)
        cutoff = datetime.date(2023, 12, 31)

        early = _make_fact(end=period, filed=datetime.date(2023, 2, 1), value=100)
        late = _make_fact(end=period, filed=datetime.date(2023, 3, 1), value=200)

        # Most recently filed should win
        result = select_best_fact_for_period([early, late], period, cutoff)
        assert result is not None
        assert result.value == 200

    def test_select_best_fact_excludes_after_cutoff(self) -> None:
        period = datetime.date(2022, 12, 31)
        cutoff = datetime.date(2023, 1, 31)  # Tight cutoff

        within = _make_fact(end=period, filed=datetime.date(2023, 1, 15))
        after = _make_fact(end=period, filed=datetime.date(2023, 2, 28))

        result = select_best_fact_for_period([within, after], period, cutoff)
        assert result is not None
        assert result.filed == datetime.date(2023, 1, 15)

    def test_select_best_fact_returns_none_when_all_excluded(self) -> None:
        period = datetime.date(2022, 12, 31)
        cutoff = datetime.date(2022, 12, 31)  # Cutoff before any filing

        fact = _make_fact(end=period, filed=datetime.date(2023, 2, 1))
        result = select_best_fact_for_period([fact], period, cutoff)
        assert result is None

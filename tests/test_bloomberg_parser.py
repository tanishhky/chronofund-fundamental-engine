"""
test_bloomberg_parser.py – Tests for Bloomberg XLSX/PDF parsers.

Tests estimate column exclusion, LTM exclusion, scale detection,
and the column header parsing logic.
"""

from __future__ import annotations

import datetime

import pytest

from fundamental_engine.bloomberg.parsers.xlsx_generic import XLSXGenericParser
from fundamental_engine.bloomberg.mapping import BloombergMapper
from fundamental_engine.types import (
    BloombergColumn,
    DataSource,
    RawStatementTable,
    StatementType,
)


def _make_raw_table(
    columns: list[BloombergColumn],
    data: dict | None = None,
) -> RawStatementTable:
    return RawStatementTable(
        ticker="AAPL",
        statement_type=StatementType.INCOME,
        columns=columns,
        data=data or {"Revenue": {col.label: 1_000.0 for col in columns}},
        scale=1_000_000.0,  # In millions
        source=DataSource.BLOOMBERG_XLSX,
    )


def _make_col(
    label: str,
    fiscal_year: int | None = None,
    is_estimate: bool = False,
    is_ltm: bool = False,
    period_end: datetime.date | None = None,
) -> BloombergColumn:
    # Derive fiscal year from label if not provided
    import re
    if fiscal_year is None:
        m = re.search(r"(19|20)\d{2}", label)
        fiscal_year = int(m.group()) if m else None
    return BloombergColumn(
        label=label,
        fiscal_year=fiscal_year,
        is_estimate=is_estimate,
        is_ltm=is_ltm,
        is_restated=False,
        period_end=period_end or (datetime.date(fiscal_year, 12, 31) if fiscal_year else None),
    )


class TestXLSXParserColumnParsing:
    """Tests for the column header parser embedded in XLSXGenericParser."""

    def setup_method(self) -> None:
        self._parser = XLSXGenericParser(allow_ltm=False, allow_estimates=False)

    def test_actual_column_detected(self) -> None:
        col = self._parser._parse_column("2021A", datetime.date(2022, 12, 31))
        assert col.fiscal_year == 2021
        assert col.is_estimate is False
        assert col.is_ltm is False

    def test_estimate_column_detected(self) -> None:
        col = self._parser._parse_column("2022E", datetime.date(2022, 12, 31))
        assert col.is_estimate is True

    def test_ltm_column_detected(self) -> None:
        col = self._parser._parse_column("LTM", datetime.date(2022, 12, 31))
        assert col.is_ltm is True

    def test_restated_column_detected(self) -> None:
        col = self._parser._parse_column("2020 Restated", datetime.date(2022, 12, 31))
        assert col.is_restated is True
        assert col.fiscal_year == 2020

    def test_period_end_is_dec_31(self) -> None:
        col = self._parser._parse_column("2021A", datetime.date(2022, 12, 31))
        assert col.period_end == datetime.date(2021, 12, 31)


class TestBloombergMapper:
    """Tests for Bloomberg → standardized field mapping."""

    def setup_method(self) -> None:
        self._mapper = BloombergMapper()

    def test_estimate_columns_excluded_by_default(self) -> None:
        """Estimate columns must be stripped from output rows."""
        actual_col = _make_col("2021A", is_estimate=False)
        estimate_col = _make_col("2022E", is_estimate=True)

        raw = _make_raw_table([actual_col, estimate_col])
        cutoff = datetime.date(2022, 12, 31)

        rows = self._mapper.map_to_rows(raw, cutoff)

        # Only the 2021A actual column should produce a row
        assert len(rows) == 1
        assert rows[0]["period_end"] == datetime.date(2021, 12, 31)

    def test_ltm_columns_excluded_by_default(self) -> None:
        actual_col = _make_col("2021A")
        ltm_col = _make_col("LTM", fiscal_year=None, is_ltm=True, period_end=None)

        raw = _make_raw_table([actual_col, ltm_col])
        cutoff = datetime.date(2022, 12, 31)

        rows = self._mapper.map_to_rows(raw, cutoff)

        assert len(rows) == 1
        assert rows[0]["period_end"] == datetime.date(2021, 12, 31)

    def test_future_columns_excluded_by_cutoff(self) -> None:
        """Columns with period_end after cutoff should be excluded."""
        past_col = _make_col("2021A", period_end=datetime.date(2021, 12, 31))
        future_col = _make_col("2023A", period_end=datetime.date(2023, 12, 31))

        raw = _make_raw_table([past_col, future_col])
        cutoff = datetime.date(2022, 1, 1)

        rows = self._mapper.map_to_rows(raw, cutoff)

        # Only 2021 should pass
        assert len(rows) == 1
        assert rows[0]["period_end"] == datetime.date(2021, 12, 31)

    def test_scale_applied_to_values(self) -> None:
        """Values should be multiplied by the scale factor (e.g., millions)."""
        col = _make_col("2021A")
        raw = RawStatementTable(
            ticker="AAPL",
            statement_type=StatementType.INCOME,
            columns=[col],
            data={"Revenue": {col.label: 365.8}},  # 365.8 million
            scale=1_000_000.0,
            source=DataSource.BLOOMBERG_XLSX,
        )
        cutoff = datetime.date(2022, 12, 31)
        rows = self._mapper.map_to_rows(raw, cutoff)

        assert len(rows) == 1
        # Revenue should be mapped to "revenue" field with scale applied
        assert rows[0].get("revenue") == pytest.approx(365_800_000.0)

    def test_label_normalization(self) -> None:
        """Bloomberg label 'Total Revenue' should map to 'revenue' field."""
        col = _make_col("2021A")
        raw = RawStatementTable(
            ticker="AAPL",
            statement_type=StatementType.INCOME,
            columns=[col],
            data={"Total Revenue": {col.label: 100.0}},
            scale=1.0,
            source=DataSource.BLOOMBERG_XLSX,
        )
        rows = self._mapper.map_to_rows(raw, datetime.date(2022, 12, 31))
        assert len(rows) == 1
        assert rows[0].get("revenue") == 100.0

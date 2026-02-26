"""
test_cik_mapping.py – Tests for ticker → CIK resolution.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fundamental_engine.edgar.cik_map import CIKMapper
from fundamental_engine.exceptions import CIKLookupError


# Sample response matching SEC company_tickers.json structure
_MOCK_CIK_RESPONSE = {
    "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": "789019", "ticker": "MSFT", "title": "Microsoft Corp"},
    "2": {"cik_str": "1652044", "ticker": "GOOGL", "title": "Alphabet Inc."},
    "3": {"cik_str": "1018724", "ticker": "AMZN", "title": "Amazon.com Inc."},
}


def _make_mapper_with_mock() -> CIKMapper:
    """Create a CIKMapper backed by a mock EdgarClient."""
    mock_client = MagicMock()
    mock_client.get_json.return_value = _MOCK_CIK_RESPONSE
    return CIKMapper(mock_client)


class TestCIKMapper:
    def test_resolves_known_ticker(self) -> None:
        mapper = _make_mapper_with_mock()
        cik = mapper.resolve("AAPL")
        assert cik == "0000320193"

    def test_pads_cik_to_10_digits(self) -> None:
        mapper = _make_mapper_with_mock()
        cik = mapper.resolve("AAPL")
        assert len(cik) == 10
        assert cik.startswith("0")

    def test_case_insensitive(self) -> None:
        mapper = _make_mapper_with_mock()
        assert mapper.resolve("aapl") == mapper.resolve("AAPL")
        assert mapper.resolve("Msft") == mapper.resolve("MSFT")

    def test_unknown_ticker_raises(self) -> None:
        mapper = _make_mapper_with_mock()
        with pytest.raises(CIKLookupError) as exc_info:
            mapper.resolve("FAKE_TICKER_XYZ")
        assert "FAKE_TICKER_XYZ" in str(exc_info.value)

    def test_resolve_many_skips_unknowns(self) -> None:
        mapper = _make_mapper_with_mock()
        result = mapper.resolve_many(["AAPL", "FAKE_XYZ", "MSFT"])
        assert "AAPL" in result
        assert "MSFT" in result
        assert "FAKE_XYZ" not in result

    def test_company_name(self) -> None:
        mapper = _make_mapper_with_mock()
        name = mapper.company_name("AAPL")
        assert name == "Apple Inc."

    def test_load_is_idempotent(self) -> None:
        """Calling load() twice should only hit the API once."""
        mapper = _make_mapper_with_mock()
        mapper.load()
        mapper.load()
        assert mapper._client.get_json.call_count == 1

    def test_multiple_tickers_resolved(self) -> None:
        mapper = _make_mapper_with_mock()
        result = mapper.resolve_many(["AAPL", "MSFT", "GOOGL", "AMZN"])
        assert len(result) == 4
        assert result["GOOGL"] == "0001652044"

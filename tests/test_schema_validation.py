"""
test_schema_validation.py – Tests for schema validation and accounting identities.
"""

from __future__ import annotations

import pandas as pd
import pytest

from fundamental_engine.data.schema import INCOME_SCHEMA
from fundamental_engine.data.validation import (
    assert_valid_table,
    check_balance_sheet_identity,
    check_cashflow_reconciliation,
    validate_table,
)
from fundamental_engine.exceptions import SchemaValidationError


def _make_income_row(**kwargs) -> dict:
    """Create a complete income statement row with all schema columns populated."""
    base = {col: None for col in INCOME_SCHEMA.all_column_names}
    base.update({
        "ticker": "AAPL",
        "cik": "0000320193",
        "accession": "0000320193-22-000100",
        "asof_date": "2023-02-01",
        "period_end": "2022-12-31",
        "source": "edgar",
        "revenue": 394_328_000_000.0,
        "net_income": 99_803_000_000.0,
        "ebit": 119_437_000_000.0,
    })
    base.update(kwargs)
    return base


def _make_balance_row(**kwargs) -> dict:
    base = {
        "ticker": "AAPL",
        "cik": "0000320193",
        "accession": "0000320193-22-000100",
        "asof_date": "2023-02-01",
        "period_end": "2022-12-31",
        "source": "edgar",
        "total_assets": 352_755_000_000.0,
        "total_liabilities": 302_083_000_000.0,
        "total_equity": 50_672_000_000.0,
    }
    base.update(kwargs)
    return base


class TestSchemaValidation:
    def test_valid_income_table_passes(self) -> None:
        df = pd.DataFrame([_make_income_row()])
        violations = validate_table(df, "statements_income")
        assert violations == []

    def test_missing_required_column_fails(self) -> None:
        df = pd.DataFrame([_make_income_row()])
        df = df.drop(columns=["ticker"])
        violations = validate_table(df, "statements_income")
        assert any("ticker" in v for v in violations)

    def test_assert_valid_raises_on_violation(self) -> None:
        df = pd.DataFrame([_make_income_row()])
        df = df.drop(columns=["cik"])
        with pytest.raises(SchemaValidationError) as exc_info:
            assert_valid_table(df, "statements_income")
        assert "statements_income" in str(exc_info.value)

    def test_duplicate_keys_detected(self) -> None:
        row = _make_income_row()
        df = pd.DataFrame([row, row])  # Duplicate rows
        violations = validate_table(df, "statements_income")
        assert any("duplicate" in v.lower() for v in violations)


class TestBalanceSheetIdentity:
    def test_balanced_sheet_passes(self) -> None:
        row = _make_balance_row()
        df = pd.DataFrame([row])
        result = check_balance_sheet_identity(df)
        # Use == True to handle numpy bool (not 'is True')
        assert result["identity_ok"].iloc[0] == True  # noqa: E712

    def test_slightly_off_balance_fails(self) -> None:
        """More than 1% relative error should be flagged."""
        row = _make_balance_row(
            total_assets=100_000_000.0,
            total_liabilities=80_000_000.0,
            total_equity=10_000_000.0,  # Should be 20M for balance; off by 10%
        )
        df = pd.DataFrame([row])
        result = check_balance_sheet_identity(df)
        assert result["identity_ok"].iloc[0] == False  # noqa: E712

    def test_missing_columns_returns_na(self) -> None:
        df = pd.DataFrame([{"ticker": "AAPL", "total_assets": 100.0}])
        result = check_balance_sheet_identity(df)
        assert result["identity_ok"].isna().all()

    def test_identity_ok_column_added(self) -> None:
        df = pd.DataFrame([_make_balance_row()])
        result = check_balance_sheet_identity(df)
        assert "identity_ok" in result.columns


class TestCashflowReconciliation:
    def test_reconciling_cashflow(self) -> None:
        df = pd.DataFrame([{
            "ticker": "AAPL",
            "cik": "0000320193",
            "accession": "X",
            "cfo": 100_000_000.0,
            "cfi": -50_000_000.0,
            "cff": -30_000_000.0,
            "net_change_in_cash": 20_000_000.0,
        }])
        result = check_cashflow_reconciliation(df)
        assert result["cashflow_reconciles"].iloc[0] == True  # noqa: E712

    def test_non_reconciling_cashflow(self) -> None:
        df = pd.DataFrame([{
            "ticker": "AAPL",
            "cik": "0000320193",
            "accession": "X",
            "cfo": 100_000_000.0,
            "cfi": -50_000_000.0,
            "cff": -30_000_000.0,
            "net_change_in_cash": 999_000_000.0,  # Way off
        }])
        result = check_cashflow_reconciliation(df)
        assert result["cashflow_reconciles"].iloc[0] == False  # noqa: E712

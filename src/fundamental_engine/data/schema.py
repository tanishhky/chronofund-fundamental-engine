"""
schema.py – Canonical DataFrame schema definitions for all standardized tables.

Each table is represented as a SchemaDefinition with:
- Required columns and their dtypes
- Optional columns
- Validation rules

This is the source of truth for what a 'valid' output looks like.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from fundamental_engine.constants import (
    BALANCE_COLS,
    CASHFLOW_COLS,
    COMPANY_MASTER_COLS,
    DERIVED_COLS,
    FILING_COLS,
    INCOME_COLS,
)


@dataclass
class ColumnSpec:
    """
    Specification for a single DataFrame column.

    Attributes
    ----------
    name:
        Column name.
    dtype:
        Expected pandas dtype (as a string or numpy dtype).
    required:
        If True, column must be present and non-null in at least one row.
    nullable:
        If True, NaN/None values are permitted.
    """

    name: str
    dtype: str
    required: bool = True
    nullable: bool = True


@dataclass
class SchemaDefinition:
    """
    Full schema for a named output table.

    Attributes
    ----------
    table_name:
        Canonical name (e.g. 'statements_income').
    key_columns:
        Columns that together form a unique row identifier.
    columns:
        All column specifications.
    """

    table_name: str
    key_columns: list[str]
    columns: list[ColumnSpec]

    @property
    def required_columns(self) -> list[str]:
        return [c.name for c in self.columns if c.required]

    @property
    def all_column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def empty_dataframe(self) -> pd.DataFrame:
        """Return an empty DataFrame with the correct column types."""
        dtype_map: dict[str, Any] = {c.name: _pandas_dtype(c.dtype) for c in self.columns}
        return pd.DataFrame(columns=list(dtype_map.keys())).astype(dtype_map)


def _pandas_dtype(dtype_str: str) -> Any:
    """Map a string dtype spec to a pandas-compatible dtype."""
    mapping: dict[str, Any] = {
        "str": "object",
        "string": "object",
        "float": "float64",
        "int": "Int64",   # nullable integer
        "date": "object",
        "datetime": "object",
        "bool": "bool",
    }
    return mapping.get(dtype_str, dtype_str)


# ── Schema Instances ──────────────────────────────────────────────────────────

COMPANY_MASTER_SCHEMA = SchemaDefinition(
    table_name="company_master",
    key_columns=["cik"],
    columns=[
        ColumnSpec("ticker", "str"),
        ColumnSpec("cik", "str"),
        ColumnSpec("company_name", "str"),
        ColumnSpec("sic", "str", nullable=True),
        ColumnSpec("exchange", "str", nullable=True),
    ],
)

FILINGS_SCHEMA = SchemaDefinition(
    table_name="filings",
    key_columns=["cik", "accession"],
    columns=[
        ColumnSpec("ticker", "str"),
        ColumnSpec("cik", "str"),
        ColumnSpec("accession", "str"),
        ColumnSpec("form_type", "str"),
        ColumnSpec("filing_date", "date"),
        ColumnSpec("acceptance_datetime", "datetime"),
        ColumnSpec("period_of_report", "date"),
        ColumnSpec("source", "str"),
    ],
)

INCOME_SCHEMA = SchemaDefinition(
    table_name="statements_income",
    key_columns=["cik", "accession", "period_end"],
    columns=[
        ColumnSpec("ticker", "str"),
        ColumnSpec("cik", "str"),
        ColumnSpec("accession", "str"),
        ColumnSpec("asof_date", "date"),
        ColumnSpec("period_end", "date"),
        ColumnSpec("source", "str"),
        ColumnSpec("revenue", "float", nullable=True),
        ColumnSpec("cost_of_revenue", "float", nullable=True),
        ColumnSpec("gross_profit", "float", nullable=True),
        ColumnSpec("operating_expenses", "float", nullable=True),
        ColumnSpec("ebit", "float", nullable=True),
        ColumnSpec("ebitda", "float", nullable=True),
        ColumnSpec("interest_expense", "float", nullable=True),
        ColumnSpec("pretax_income", "float", nullable=True),
        ColumnSpec("income_tax_expense", "float", nullable=True),
        ColumnSpec("net_income", "float", nullable=True),
        ColumnSpec("eps_basic", "float", nullable=True),
        ColumnSpec("eps_diluted", "float", nullable=True),
        ColumnSpec("shares_basic", "float", nullable=True),
        ColumnSpec("shares_diluted", "float", nullable=True),
    ],
)

BALANCE_SCHEMA = SchemaDefinition(
    table_name="statements_balance",
    key_columns=["cik", "accession", "period_end"],
    columns=[
        ColumnSpec("ticker", "str"),
        ColumnSpec("cik", "str"),
        ColumnSpec("accession", "str"),
        ColumnSpec("asof_date", "date"),
        ColumnSpec("period_end", "date"),
        ColumnSpec("source", "str"),
        ColumnSpec("cash_and_equivalents", "float", nullable=True),
        ColumnSpec("short_term_investments", "float", nullable=True),
        ColumnSpec("accounts_receivable", "float", nullable=True),
        ColumnSpec("inventory", "float", nullable=True),
        ColumnSpec("current_assets", "float", nullable=True),
        ColumnSpec("ppe_net", "float", nullable=True),
        ColumnSpec("goodwill", "float", nullable=True),
        ColumnSpec("intangibles", "float", nullable=True),
        ColumnSpec("total_assets", "float", nullable=True),
        ColumnSpec("accounts_payable", "float", nullable=True),
        ColumnSpec("short_term_debt", "float", nullable=True),
        ColumnSpec("current_liabilities", "float", nullable=True),
        ColumnSpec("long_term_debt", "float", nullable=True),
        ColumnSpec("total_liabilities", "float", nullable=True),
        ColumnSpec("common_equity", "float", nullable=True),
        ColumnSpec("retained_earnings", "float", nullable=True),
        ColumnSpec("total_equity", "float", nullable=True),
    ],
)

CASHFLOW_SCHEMA = SchemaDefinition(
    table_name="statements_cashflow",
    key_columns=["cik", "accession", "period_end"],
    columns=[
        ColumnSpec("ticker", "str"),
        ColumnSpec("cik", "str"),
        ColumnSpec("accession", "str"),
        ColumnSpec("asof_date", "date"),
        ColumnSpec("period_end", "date"),
        ColumnSpec("source", "str"),
        ColumnSpec("cfo", "float", nullable=True),
        ColumnSpec("capex", "float", nullable=True),
        ColumnSpec("free_cash_flow", "float", nullable=True),
        ColumnSpec("cfi", "float", nullable=True),
        ColumnSpec("cff", "float", nullable=True),
        ColumnSpec("dividends_paid", "float", nullable=True),
        ColumnSpec("share_repurchases", "float", nullable=True),
        ColumnSpec("net_change_in_cash", "float", nullable=True),
        ColumnSpec("depreciation_amortization", "float", nullable=True),
        ColumnSpec("stock_based_compensation", "float", nullable=True),
    ],
)

DERIVED_SCHEMA = SchemaDefinition(
    table_name="derived_metrics",
    key_columns=["cik", "accession", "period_end"],
    columns=[
        ColumnSpec("ticker", "str"),
        ColumnSpec("cik", "str"),
        ColumnSpec("accession", "str"),
        ColumnSpec("asof_date", "date"),
        ColumnSpec("period_end", "date"),
        ColumnSpec("source", "str"),
        ColumnSpec("gross_margin", "float", nullable=True),
        ColumnSpec("ebit_margin", "float", nullable=True),
        ColumnSpec("net_margin", "float", nullable=True),
        ColumnSpec("roa", "float", nullable=True),
        ColumnSpec("roe", "float", nullable=True),
        ColumnSpec("roic", "float", nullable=True),
        ColumnSpec("current_ratio", "float", nullable=True),
        ColumnSpec("quick_ratio", "float", nullable=True),
        ColumnSpec("debt_to_equity", "float", nullable=True),
        ColumnSpec("net_debt", "float", nullable=True),
        ColumnSpec("fcf_yield", "float", nullable=True),
    ],
)

ALL_SCHEMAS: dict[str, SchemaDefinition] = {
    "company_master": COMPANY_MASTER_SCHEMA,
    "filings": FILINGS_SCHEMA,
    "statements_income": INCOME_SCHEMA,
    "statements_balance": BALANCE_SCHEMA,
    "statements_cashflow": CASHFLOW_SCHEMA,
    "derived_metrics": DERIVED_SCHEMA,
}

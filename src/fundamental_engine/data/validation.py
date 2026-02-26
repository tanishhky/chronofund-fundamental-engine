"""
validation.py – Runtime schema and accounting identity validation.

Validates DataFrames against SchemaDefinition and checks accounting identities
(balance sheet equation, cash flow reconciliation).
"""

from __future__ import annotations

import logging

import pandas as pd

from fundamental_engine.constants import BALANCE_SHEET_TOLERANCE
from fundamental_engine.data.schema import ALL_SCHEMAS, SchemaDefinition
from fundamental_engine.exceptions import SchemaValidationError

logger = logging.getLogger(__name__)


# ── Schema Validation ─────────────────────────────────────────────────────────

def validate_table(df: pd.DataFrame, table_name: str) -> list[str]:
    """
    Validate a DataFrame against its registered schema.

    Parameters
    ----------
    df:
        DataFrame to validate.
    table_name:
        Name of the table (must exist in ALL_SCHEMAS).

    Returns
    -------
    List of violation strings. Empty list means valid.

    Raises
    ------
    KeyError: if ``table_name`` is not in ALL_SCHEMAS.
    """
    schema: SchemaDefinition = ALL_SCHEMAS[table_name]
    violations: list[str] = []

    # Check required columns presence
    for col in schema.required_columns:
        if col not in df.columns:
            violations.append(f"Missing required column: '{col}'")

    # Check for completely null required non-nullable columns
    for spec in schema.columns:
        if spec.name in df.columns and not spec.nullable:
            null_count = df[spec.name].isna().sum()
            if null_count > 0:
                violations.append(
                    f"Column '{spec.name}' is non-nullable but has {null_count} null values"
                )

    # Check key uniqueness
    key_cols = [c for c in schema.key_columns if c in df.columns]
    if key_cols and df.duplicated(subset=key_cols).any():
        dup_count = df.duplicated(subset=key_cols).sum()
        violations.append(
            f"Key columns {key_cols} are not unique: {dup_count} duplicate rows"
        )

    return violations


def assert_valid_table(df: pd.DataFrame, table_name: str) -> None:
    """
    Validate a table and raise SchemaValidationError if there are violations.

    Parameters
    ----------
    df:
        DataFrame to validate.
    table_name:
        Table name to validate against.

    Raises
    ------
    SchemaValidationError: on any validation failure.
    """
    violations = validate_table(df, table_name)
    if violations:
        raise SchemaValidationError(table_name, violations)
    logger.debug("Table '%s' passed schema validation (%d rows)", table_name, len(df))


# ── Accounting Identity Checks ────────────────────────────────────────────────

def check_balance_sheet_identity(balance_df: pd.DataFrame) -> pd.DataFrame:
    """
    Check the accounting identity: Assets ≈ Liabilities + Equity.

    Rows that violate the identity beyond the configured tolerance trigger a
    WARNING log entry and an 'identity_ok' flag column on the output.

    Parameters
    ----------
    balance_df:
        The standardized balance sheet DataFrame.

    Returns
    -------
    pd.DataFrame with an added boolean column 'identity_ok'.
    """
    df = balance_df.copy()
    has_required = all(
        col in df.columns
        for col in ("total_assets", "total_liabilities", "total_equity")
    )
    if not has_required:
        logger.warning(
            "Cannot check balance sheet identity: missing required columns. "
            "Need total_assets, total_liabilities, total_equity."
        )
        df["identity_ok"] = pd.NA
        return df

    liab_plus_equity = df["total_liabilities"].fillna(0) + df["total_equity"].fillna(0)
    assets = df["total_assets"].fillna(0)

    # Relative error; avoid division by zero
    with_assets = assets.abs() > 0
    relative_error = pd.Series(index=df.index, dtype="float64")
    relative_error[with_assets] = (
        (assets[with_assets] - liab_plus_equity[with_assets]).abs()
        / assets[with_assets].abs()
    )
    relative_error[~with_assets] = pd.NA

    identity_ok = relative_error <= BALANCE_SHEET_TOLERANCE
    df["identity_ok"] = identity_ok

    violations = df[~identity_ok & identity_ok.notna()]
    if not violations.empty:
        for _, row in violations.iterrows():
            logger.warning(
                "Balance sheet identity violation: ticker=%s accession=%s "
                "assets=%.0f liab+eq=%.0f rel_error=%.4f",
                row.get("ticker", "?"),
                row.get("accession", "?"),
                row.get("total_assets", float("nan")),
                liab_plus_equity[row.name],
                relative_error[row.name],
            )

    return df


def check_cashflow_reconciliation(
    cashflow_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Check: CFO + CFI + CFF ≈ net_change_in_cash.

    Parameters
    ----------
    cashflow_df:
        The standardized cash flow DataFrame.

    Returns
    -------
    pd.DataFrame with an added boolean column 'cashflow_reconciles'.
    """
    df = cashflow_df.copy()
    needed = {"cfo", "cfi", "cff", "net_change_in_cash"}
    if not needed.issubset(df.columns):
        df["cashflow_reconciles"] = pd.NA
        return df

    computed = (
        df["cfo"].fillna(0)
        + df["cfi"].fillna(0)
        + df["cff"].fillna(0)
    )
    reported = df["net_change_in_cash"].fillna(0)

    diff = (computed - reported).abs()
    # Tolerance: 1% of the larger of computed/reported, minimum $1M
    tolerance = (computed.abs().combine(reported.abs(), max) * 0.01).clip(lower=1_000_000)
    df["cashflow_reconciles"] = diff <= tolerance

    bad = df[~df["cashflow_reconciles"]]
    for _, row in bad.iterrows():
        logger.warning(
            "Cash flow reconciliation error: ticker=%s accession=%s diff=%.0f",
            row.get("ticker", "?"),
            row.get("accession", "?"),
            diff[row.name],
        )

    return df

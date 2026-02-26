"""
mapping.py – Maps Bloomberg RawStatementTable to standardized row dicts.

Bloomberg field labels vary by report type. This module normalizes them
to the unified schema column names.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from fundamental_engine.types import BloombergColumn, DataSource, RawStatementTable, StatementType

logger = logging.getLogger(__name__)

# ── Bloomberg label → standardized field name ─────────────────────────────────
# Keys are lowercased, stripped labels from Bloomberg tables.

INCOME_LABEL_MAP: dict[str, str] = {
    "revenue": "revenue",
    "net revenue": "revenue",
    "total revenue": "revenue",
    "net sales": "revenue",
    "sales": "revenue",
    "cost of goods sold": "cost_of_revenue",
    "cost of revenue": "cost_of_revenue",
    "cost of sales": "cost_of_revenue",
    "gross profit": "gross_profit",
    "operating expenses": "operating_expenses",
    "total operating expenses": "operating_expenses",
    "ebit": "ebit",
    "operating income": "ebit",
    "operating profit": "ebit",
    "ebitda": "ebitda",
    "interest expense": "interest_expense",
    "pretax income": "pretax_income",
    "income before tax": "pretax_income",
    "income tax expense": "income_tax_expense",
    "provision for income taxes": "income_tax_expense",
    "net income": "net_income",
    "net income (loss)": "net_income",
    "eps basic": "eps_basic",
    "basic eps": "eps_basic",
    "eps diluted": "eps_diluted",
    "diluted eps": "eps_diluted",
    "shares outstanding basic": "shares_basic",
    "shares outstanding diluted": "shares_diluted",
}

BALANCE_LABEL_MAP: dict[str, str] = {
    "cash and equivalents": "cash_and_equivalents",
    "cash & equivalents": "cash_and_equivalents",
    "cash and cash equivalents": "cash_and_equivalents",
    "short-term investments": "short_term_investments",
    "short term investments": "short_term_investments",
    "accounts receivable": "accounts_receivable",
    "receivables": "accounts_receivable",
    "inventories": "inventory",
    "inventory": "inventory",
    "total current assets": "current_assets",
    "current assets": "current_assets",
    "property plant & equipment": "ppe_net",
    "property plant and equipment": "ppe_net",
    "ppe net": "ppe_net",
    "goodwill": "goodwill",
    "intangible assets": "intangibles",
    "intangibles": "intangibles",
    "total assets": "total_assets",
    "assets": "total_assets",
    "accounts payable": "accounts_payable",
    "short-term debt": "short_term_debt",
    "current portion of long-term debt": "short_term_debt",
    "total current liabilities": "current_liabilities",
    "current liabilities": "current_liabilities",
    "long-term debt": "long_term_debt",
    "long term debt": "long_term_debt",
    "total liabilities": "total_liabilities",
    "liabilities": "total_liabilities",
    "stockholders equity": "common_equity",
    "shareholders equity": "common_equity",
    "common equity": "common_equity",
    "retained earnings": "retained_earnings",
    "total equity": "total_equity",
    "total shareholders equity": "total_equity",
}

CASHFLOW_LABEL_MAP: dict[str, str] = {
    "cash from operations": "cfo",
    "net cash from operating activities": "cfo",
    "operating cash flow": "cfo",
    "capital expenditures": "capex",
    "capex": "capex",
    "cash from investing": "cfi",
    "net cash from investing activities": "cfi",
    "cash from financing": "cff",
    "net cash from financing activities": "cff",
    "dividends paid": "dividends_paid",
    "share repurchases": "share_repurchases",
    "net change in cash": "net_change_in_cash",
    "change in cash": "net_change_in_cash",
    "depreciation & amortization": "depreciation_amortization",
    "depreciation and amortization": "depreciation_amortization",
    "d&a": "depreciation_amortization",
    "stock-based compensation": "stock_based_compensation",
    "share-based compensation": "stock_based_compensation",
    "free cash flow": "free_cash_flow",
}

_LABEL_MAPS: dict[StatementType, dict[str, str]] = {
    StatementType.INCOME: INCOME_LABEL_MAP,
    StatementType.BALANCE: BALANCE_LABEL_MAP,
    StatementType.CASHFLOW: CASHFLOW_LABEL_MAP,
}


class BloombergMapper:
    """
    Maps Bloomberg RawStatementTable instances to lists of standardized row dicts.
    """

    def map_to_rows(
        self,
        raw: RawStatementTable,
        cutoff_date: datetime.date,
    ) -> list[dict[str, Any]]:
        """
        Convert a RawStatementTable into a list of standardized row dicts.

        Each column in the raw table that passes PIT cutoff becomes one row.

        Parameters
        ----------
        raw:
            Parsed Bloomberg statement table.
        cutoff_date:
            Columns whose period_end > cutoff_date are excluded.

        Returns
        -------
        list[dict] where each dict represents one period row.
        """
        label_map = _LABEL_MAPS.get(raw.statement_type, {})
        rows: list[dict[str, Any]] = []

        for col in raw.columns:
            # PIT gate: skip columns with period_end after cutoff
            if col.period_end is not None and col.period_end > cutoff_date:
                logger.debug(
                    "Skipping Bloomberg column '%s' (period_end=%s > cutoff=%s)",
                    col.label, col.period_end, cutoff_date,
                )
                continue

            # Skip estimate columns (unless explicitly allowed)
            if col.is_estimate:
                logger.debug("Skipping estimate column '%s' for %s", col.label, raw.ticker)
                continue

            # Skip LTM columns (unless explicitly allowed)
            if col.is_ltm:
                logger.debug("Skipping LTM column '%s' for %s", col.label, raw.ticker)
                continue

            row: dict[str, Any] = {
                "ticker": raw.ticker,
                "cik": None,  # Bloomberg doesn't provide CIK; enriched later
                "accession": f"BBG_{raw.ticker}_{col.label}",
                "asof_date": col.period_end,
                "period_end": col.period_end,
                "source": raw.source.value,
                "_statement_type": raw.statement_type.value,
            }

            for raw_label, values_by_col in raw.data.items():
                normalized = raw_label.strip().lower()
                std_field = label_map.get(normalized)
                if std_field is None:
                    continue

                raw_val = values_by_col.get(col.label)
                if raw_val is None:
                    row[std_field] = None
                else:
                    try:
                        scaled_val = float(raw_val) * raw.scale
                        row[std_field] = scaled_val
                    except (ValueError, TypeError):
                        row[std_field] = None

            rows.append(row)

        return rows

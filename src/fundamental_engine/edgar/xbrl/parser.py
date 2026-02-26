"""
parser.py – Assembles standardized DataFrames from XBRLFact objects.

Orchestrates context selection and tag mapping to produce rows for
statements_income, statements_balance, and statements_cashflow.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import pandas as pd

from fundamental_engine.edgar.xbrl.contexts import (
    filter_facts_by_period_type,
    group_facts_by_period_end,
    prefer_consolidated,
    select_best_fact_for_period,
)
from fundamental_engine.edgar.xbrl.mapper import FIELD_TO_MAPPING, TAG_PRIORITY_MAP
from fundamental_engine.types import DataSource, XBRLContextType, XBRLFact
from fundamental_engine.utils.dates import is_annual_period

logger = logging.getLogger(__name__)


class XBRLParser:
    """
    Converts a dict of {tag: [XBRLFact]} into standardized DataFrames.

    Parameters
    ----------
    ticker:
        Equity ticker (for output row labeling).
    cik:
        Zero-padded 10-digit CIK.
    """

    def __init__(self, ticker: str, cik: str) -> None:
        self._ticker = ticker
        self._cik = cik

    def build_income_rows(
        self,
        facts: dict[str, list[XBRLFact]],
        filing_accession: str,
        period_end: datetime.date,
        cutoff_date: datetime.date,
        asof_date: datetime.date,
        annual: bool = True,
    ) -> dict[str, Any] | None:
        """
        Build a single income statement row for a given period.

        Parameters
        ----------
        facts:
            All XBRL facts keyed by '{namespace}:{tag}'.
        filing_accession:
            The filing accession number for this row.
        period_end:
            Fiscal period end date.
        cutoff_date:
            PIT cutoff; facts filed after this date are excluded.
        asof_date:
            The acceptance date of the filing (populates 'asof_date' column).
        annual:
            True for annual, False for quarterly durations.

        Returns
        -------
        dict row or None if no primary facts (revenue/net_income) are found.
        """
        row: dict[str, Any] = {
            "ticker": self._ticker,
            "cik": self._cik,
            "accession": filing_accession,
            "asof_date": asof_date,
            "period_end": period_end,
            "source": DataSource.EDGAR.value,
        }

        income_fields = [
            m.standard_field for m in TAG_PRIORITY_MAP
            if m.context_type == "duration"
        ]

        found_any = False
        for field_name in income_fields:
            value = self._resolve_duration_field(
                field_name, facts, period_end, cutoff_date, annual
            )
            row[field_name] = value
            if value is not None:
                found_any = True

        # Fallback EBITDA calculation (EBIT + D&A) if not explicitly tagged
        if row.get("ebitda") is None:
            ebit = row.get("ebit")
            # D&A is usually mapped under cash flow, but we can fetch it explicitly here
            # for the income statement duration if needed, or look up mapping
            da_mapping = FIELD_TO_MAPPING.get("depreciation_amortization")
            da_val = None
            if da_mapping:
                for full_tag in da_mapping.tags:
                    candidates = facts.get(full_tag, [])
                    filtered = filter_facts_by_period_type(
                        candidates, XBRLContextType.DURATION, annual=annual
                    )
                    best = select_best_fact_for_period(filtered, period_end, cutoff_date)
                    if best is not None:
                        sign = -1.0 if da_mapping.sign_flip else 1.0
                        da_val = best.value * sign
                        break
            
            if ebit is not None and da_val is not None:
                row["ebitda"] = ebit + da_val
                found_any = True

        if not found_any:
            logger.debug(
                "No income facts found for %s accession=%s period=%s",
                self._ticker, filing_accession, period_end,
            )
            return None

        return row

    def build_balance_rows(
        self,
        facts: dict[str, list[XBRLFact]],
        filing_accession: str,
        period_end: datetime.date,
        cutoff_date: datetime.date,
        asof_date: datetime.date,
    ) -> dict[str, Any] | None:
        """Build a balance sheet row for a given period end (instant context)."""
        row: dict[str, Any] = {
            "ticker": self._ticker,
            "cik": self._cik,
            "accession": filing_accession,
            "asof_date": asof_date,
            "period_end": period_end,
            "source": DataSource.EDGAR.value,
        }

        balance_fields = [
            m.standard_field for m in TAG_PRIORITY_MAP
            if m.context_type == "instant"
        ]

        found_any = False
        for field_name in balance_fields:
            value = self._resolve_instant_field(
                field_name, facts, period_end, cutoff_date
            )
            row[field_name] = value
            if value is not None:
                found_any = True

        # Fallback for accounting identity (Assets = Liabilities + Equity)
        assets = row.get("total_assets")
        liab = row.get("total_liabilities")
        equity = row.get("total_equity")

        if assets is None and liab is not None and equity is not None:
            row["total_assets"] = liab + equity
            found_any = True
        elif liab is None and assets is not None and equity is not None:
            row["total_liabilities"] = assets - equity
            found_any = True
        elif equity is None and assets is not None and liab is not None:
            row["total_equity"] = assets - liab
            found_any = True

        if not found_any:
            return None

        return row

    def build_cashflow_rows(
        self,
        facts: dict[str, list[XBRLFact]],
        filing_accession: str,
        period_end: datetime.date,
        cutoff_date: datetime.date,
        asof_date: datetime.date,
        annual: bool = True,
    ) -> dict[str, Any] | None:
        """Build a cash flow row for a given period. Same pattern as income."""
        row: dict[str, Any] = {
            "ticker": self._ticker,
            "cik": self._cik,
            "accession": filing_accession,
            "asof_date": asof_date,
            "period_end": period_end,
            "source": DataSource.EDGAR.value,
        }

        cashflow_fields = [
            m.standard_field for m in TAG_PRIORITY_MAP
            if m.context_type == "duration"
        ]

        found_any = False
        for field_name in cashflow_fields:
            mapping = FIELD_TO_MAPPING.get(field_name)
            if mapping is None:
                continue
            value = self._resolve_duration_field(
                field_name, facts, period_end, cutoff_date, annual
            )
            if value is not None and mapping.sign_flip:
                value = abs(value)  # Store capex/dividends as positive numbers
            row[field_name] = value
            if value is not None:
                found_any = True

        # Compute FCF = CFO - CapEx
        cfo = row.get("cfo")
        capex = row.get("capex")
        if cfo is not None and capex is not None:
            row["free_cash_flow"] = cfo - capex
            found_any = True

        if not found_any:
            return None

        return row

    # ── Private resolution helpers ────────────────────────────────────────────

    def _resolve_duration_field(
        self,
        field_name: str,
        facts: dict[str, list[XBRLFact]],
        period_end: datetime.date,
        cutoff_date: datetime.date,
        annual: bool,
    ) -> float | None:
        mapping = FIELD_TO_MAPPING.get(field_name)
        if mapping is None:
            return None

        for full_tag in mapping.tags:
            candidates = facts.get(full_tag, [])
            # Filter to the right period type (annual vs quarterly duration)
            filtered = filter_facts_by_period_type(
                candidates,
                XBRLContextType.DURATION,
                annual=annual,
            )
            # Frame preference is applied inside select_best_fact_for_period
            # AFTER period matching — calling prefer_consolidated before period
            # matching would drop facts from years where no frame exists if OTHER
            # years for the same tag do have frames.
            best = select_best_fact_for_period(filtered, period_end, cutoff_date)
            if best is not None:
                sign = -1.0 if mapping.sign_flip else 1.0
                return best.value * sign

        return None

    def _resolve_instant_field(
        self,
        field_name: str,
        facts: dict[str, list[XBRLFact]],
        period_end: datetime.date,
        cutoff_date: datetime.date,
    ) -> float | None:
        mapping = FIELD_TO_MAPPING.get(field_name)
        if mapping is None:
            return None

        for full_tag in mapping.tags:
            candidates = facts.get(full_tag, [])
            filtered = filter_facts_by_period_type(
                candidates,
                XBRLContextType.INSTANT,
                annual=True,  # irrelevant for instant—just pass True
            )
            # Frame preference applied inside select_best_fact_for_period
            best = select_best_fact_for_period(filtered, period_end, cutoff_date)
            if best is not None:
                return best.value

        return None

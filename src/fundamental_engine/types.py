"""
types.py – Shared domain types, dataclasses, and TypedDicts.
All data flowing through the engine uses these types.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd


# ── Enumerations ──────────────────────────────────────────────────────────────

class DataSource(str, Enum):
    """Origin of the financial data."""
    EDGAR = "edgar"
    BLOOMBERG_XLSX = "bloomberg_xlsx"
    BLOOMBERG_PDF = "bloomberg_pdf"


class StatementType(str, Enum):
    """Financial statement category."""
    INCOME = "income"
    BALANCE = "balance"
    CASHFLOW = "cashflow"
    DERIVED = "derived"


class FilingPeriodType(str, Enum):
    """Annual vs quarterly filing."""
    ANNUAL = "annual"
    QUARTERLY = "quarterly"


class XBRLContextType(str, Enum):
    """Whether the XBRL fact spans a duration or is a point-in-time instant."""
    DURATION = "duration"
    INSTANT = "instant"


# ── Request / Result types ────────────────────────────────────────────────────

@dataclass
class SnapshotRequest:
    """
    Describes what data to pull and when.

    Attributes
    ----------
    tickers:
        List of equity tickers to include.
    cutoff_date:
        Strict cutoff. Only filings with acceptance_datetime <= cutoff_date are included.
    period_type:
        Annual, quarterly, or both.
    source:
        Which data source to use.
    include_amendments:
        Whether to prefer amended filings (10-K/A).
    allow_ltm:
        Whether LTM columns are allowed (should remain False for PIT research).
    allow_estimates:
        Whether estimate columns are allowed (must remain False for backtests).
    """

    tickers: list[str]
    cutoff_date: datetime.date
    period_type: FilingPeriodType = FilingPeriodType.ANNUAL
    source: DataSource = DataSource.EDGAR
    include_amendments: bool = True
    allow_ltm: bool = False
    allow_estimates: bool = False


@dataclass
class CoverageReport:
    """
    Documents what data is present or missing after snapshot builds.

    Attributes
    ----------
    total_tickers:
        Number of tickers requested.
    found_tickers:
        Tickers for which at least one filing was found.
    missing_tickers:
        Tickers with no filings found.
    missing_fields:
        {ticker: [field_name, ...]} for fields that could not be populated.
    filing_counts:
        {ticker: count} of filings selected per ticker.
    """

    total_tickers: int
    found_tickers: list[str]
    missing_tickers: list[str]
    missing_fields: dict[str, list[str]] = field(default_factory=dict)
    filing_counts: dict[str, int] = field(default_factory=dict)

    @property
    def coverage_ratio(self) -> float:
        """Fraction of requested tickers with at least one filing."""
        if self.total_tickers == 0:
            return 0.0
        return len(self.found_tickers) / self.total_tickers


@dataclass
class SnapshotResult:
    """
    Output of a snapshot build operation.

    Attributes
    ----------
    cutoff:
        The cutoff date used when building this snapshot.
    tables:
        Dictionary of standardized DataFrames keyed by table name
        (e.g. 'statements_income', 'statements_balance', etc.).
    coverage_report:
        Summary of coverage and missing data.
    """

    cutoff: datetime.date
    tables: dict[str, pd.DataFrame]
    coverage_report: CoverageReport


# ── EDGAR domain types ────────────────────────────────────────────────────────

@dataclass
class FilingRecord:
    """
    Minimal metadata for a single SEC filing.

    Attributes
    ----------
    cik:
        SEC CIK number as a zero-padded 10-digit string.
    accession:
        Full accession number like '0001234567-23-000001'.
    form_type:
        Form type string, e.g. '10-K'.
    filing_date:
        Date the filing appeared on EDGAR (date only).
    acceptance_datetime:
        Precise datetime when filing was accepted by SEC.
    period_of_report:
        Fiscal period end date.
    """

    cik: str
    accession: str
    form_type: str
    filing_date: datetime.date
    acceptance_datetime: datetime.datetime
    period_of_report: datetime.date
    ticker: str = ""  # Equity ticker; set by FilingsIndex during resolution


@dataclass
class XBRLFact:
    """
    A single XBRL fact extracted from SEC companyfacts endpoint.

    Attributes
    ----------
    tag:
        GAAP/DEI concept name, e.g. 'Revenues'.
    namespace:
        XBRL namespace, e.g. 'us-gaap'.
    value:
        Numeric value of the fact.
    unit:
        Unit string ('USD', 'shares', etc.).
    start:
        Period start date for duration contexts; None for instant.
    end:
        Period end date (or instant date).
    accession:
        Accession number of the filing this fact belongs to.
    form:
        Form type string linked to this fact.
    frame:
        Optional frame label (e.g. 'CY2022Q4I').
    filed:
        Date fact was filed.
    """

    tag: str
    namespace: str
    value: float
    unit: str
    start: datetime.date | None
    end: datetime.date
    accession: str
    form: str
    frame: str | None
    filed: datetime.date


# ── Bloomberg domain types ────────────────────────────────────────────────────

@dataclass
class BloombergColumn:
    """
    Represents one date column in a Bloomberg financial table.

    Attributes
    ----------
    label:
        Original column header (e.g. '2021A', '2022E', 'LTM').
    fiscal_year:
        Parsed integer fiscal year.
    is_estimate:
        True if the column represents a forward estimate.
    is_ltm:
        True if this is an LTM/TTM column.
    is_restated:
        True if Bloomberg marked this as restated.
    period_end:
        Best-guess period end date.
    """

    label: str
    fiscal_year: int | None
    is_estimate: bool
    is_ltm: bool
    is_restated: bool
    period_end: datetime.date | None


@dataclass
class RawStatementTable:
    """
    A table of financial data extracted from a Bloomberg source before mapping.

    Attributes
    ----------
    ticker:
        Equity ticker.
    statement_type:
        Income, balance, or cashflow.
    columns:
        Parsed column descriptors.
    data:
        Raw key→{column_label: value} dictionary.
    scale:
        Multiplier detected from the file (e.g. 1_000_000 for 'in millions').
    source:
        Which data source produced this.
    """

    ticker: str
    statement_type: StatementType
    columns: list[BloombergColumn]
    data: dict[str, dict[str, Any]]
    scale: float
    source: DataSource

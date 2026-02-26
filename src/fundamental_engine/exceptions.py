"""
exceptions.py – Custom exception hierarchy for the fundamental engine.

All exceptions carry enough context to diagnose what went wrong at which stage.
"""

from __future__ import annotations

import datetime


class FundamentalEngineError(Exception):
    """Base exception for the fundamental engine. All engine errors inherit from this."""


class FilingNotFoundError(FundamentalEngineError):
    """
    Raised when no filing can be located for a given ticker / period / cutoff combination.

    Attributes
    ----------
    ticker:
        The equity ticker that was looked up.
    cutoff_date:
        The cutoff date that was in effect.
    period_end:
        The fiscal period end requested (optional).
    """

    def __init__(
        self,
        ticker: str,
        cutoff_date: datetime.date,
        period_end: datetime.date | None = None,
        message: str | None = None,
    ) -> None:
        self.ticker = ticker
        self.cutoff_date = cutoff_date
        self.period_end = period_end
        default_msg = (
            f"No filing found for ticker='{ticker}' with cutoff={cutoff_date}"
            + (f" period_end={period_end}" if period_end else "")
        )
        super().__init__(message or default_msg)


class XBRLParseError(FundamentalEngineError):
    """
    Raised when an XBRL document cannot be parsed.

    Attributes
    ----------
    accession:
        The accession number of the filing being parsed.
    detail:
        Additional diagnostic information.
    """

    def __init__(self, accession: str, detail: str) -> None:
        self.accession = accession
        self.detail = detail
        super().__init__(f"XBRL parse error in accession='{accession}': {detail}")


class SchemaValidationError(FundamentalEngineError):
    """
    Raised when a DataFrame does not comply with the expected standardized schema.

    Attributes
    ----------
    table_name:
        Name of the table that failed validation.
    violations:
        List of human-readable violation descriptions.
    """

    def __init__(self, table_name: str, violations: list[str]) -> None:
        self.table_name = table_name
        self.violations = violations
        joined = "; ".join(violations)
        super().__init__(f"Schema validation failed for table='{table_name}': {joined}")


class CutoffViolationError(FundamentalEngineError):
    """
    Raised when data would violate point-in-time cutoff integrity.

    This is the most critical safety exception in the engine.
    It is raised when:
    - An acceptance_datetime is later than the cutoff_date.
    - Restated data with a later availability date would be included.
    - An estimate column would be included in non-estimate mode.

    Attributes
    ----------
    ticker:
        The equity ticker involved.
    accession:
        The filing accession (if applicable).
    acceptance_datetime:
        The actual acceptance time that caused the violation.
    cutoff_date:
        The cutoff date that was in effect.
    """

    def __init__(
        self,
        ticker: str,
        cutoff_date: datetime.date,
        acceptance_datetime: datetime.datetime | None = None,
        accession: str | None = None,
        reason: str | None = None,
    ) -> None:
        self.ticker = ticker
        self.cutoff_date = cutoff_date
        self.acceptance_datetime = acceptance_datetime
        self.accession = accession

        if reason:
            msg = f"Cutoff violation for ticker='{ticker}': {reason}"
        elif acceptance_datetime:
            msg = (
                f"Cutoff violation: filing for ticker='{ticker}' (accession={accession}) "
                f"was accepted at {acceptance_datetime} which is after cutoff {cutoff_date}"
            )
        else:
            msg = f"Cutoff violation detected for ticker='{ticker}' at cutoff={cutoff_date}"

        super().__init__(msg)


class CIKLookupError(FundamentalEngineError):
    """
    Raised when a ticker cannot be resolved to a CIK number.

    Attributes
    ----------
    ticker:
        The ticker that was looked up.
    """

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(f"CIK resolution failed for ticker='{ticker}'")


class RateLimitError(FundamentalEngineError):
    """Raised when SEC rate limit is exceeded and retries are exhausted."""


class BloombergParseError(FundamentalEngineError):
    """
    Raised when a Bloomberg file cannot be parsed.

    Attributes
    ----------
    filepath:
        Path to the file that failed parsing.
    detail:
        Diagnostic detail.
    """

    def __init__(self, filepath: str, detail: str) -> None:
        self.filepath = filepath
        self.detail = detail
        super().__init__(f"Bloomberg parse error in '{filepath}': {detail}")

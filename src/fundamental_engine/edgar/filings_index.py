"""
filings_index.py – Fetches and filters the filing list for a given CIK.

Implements the core point-in-time cutoff logic:
  - Only filings whose acceptance_datetime ≤ cutoff are included.
  - Optionally filters to annual (10-K) or quarterly (10-Q) forms.
  - Optionally prefers amendments (10-K/A) over original filings.
"""

from __future__ import annotations

import datetime
import logging
from typing import Sequence

from fundamental_engine.config import EngineConfig
from fundamental_engine.constants import (
    ALL_SUPPORTED_FORMS,
    ANNUAL_FORM_TYPES,
    EDGAR_SUBMISSIONS_URL,
    QUARTERLY_FORM_TYPES,
)
from fundamental_engine.edgar.client import EdgarClient
from fundamental_engine.exceptions import FilingNotFoundError
from fundamental_engine.types import FilingPeriodType, FilingRecord
from fundamental_engine.utils.dates import is_within_cutoff, parse_date, parse_datetime

logger = logging.getLogger(__name__)


class FilingsIndex:
    """
    Fetches the full filing history for a single company (by CIK) and
    applies point-in-time cutoff filtering.

    Parameters
    ----------
    client:
        Configured EdgarClient.
    config:
        Engine config (controls amendment preference).
    """

    def __init__(self, client: EdgarClient, config: EngineConfig) -> None:
        self._client = client
        self._config = config

    def get_filings(
        self,
        cik: str,
        ticker: str,
        cutoff_date: datetime.date,
        period_type: FilingPeriodType = FilingPeriodType.ANNUAL,
    ) -> list[FilingRecord]:
        """
        Return all filings for a CIK that are available as of ``cutoff_date``.

        Parameters
        ----------
        cik:
            Zero-padded 10-digit CIK.
        ticker:
            Equity ticker (used for logging / error messages only).
        cutoff_date:
            Strict cutoff. Only filings with acceptanceDateTime ≤ cutoff_date are returned.
        period_type:
            Filter to annual, quarterly, or all filings.

        Returns
        -------
        list[FilingRecord] sorted by period_of_report descending.

        Raises
        ------
        FilingNotFoundError: if no qualifying filings exist.
        """
        cik_int = int(cik)
        url = EDGAR_SUBMISSIONS_URL.format(cik=cik_int)
        raw = self._client.get_json(url)

        allowed_forms = self._get_allowed_forms(period_type)

        # Parse the primary (most recent) batch
        records = self._parse_filings(raw, cik, ticker, cutoff_date, allowed_forms)

        # Fetch older archive batches if needed (SEC paginates older filings)
        archive_files = raw.get("filings", {}).get("files", [])
        for archive in archive_files:
            archive_name = archive.get("name", "")
            if not archive_name:
                continue
            # Only fetch if the archive covers the cutoff period
            filing_to_str = archive.get("filingTo", "")
            if filing_to_str:
                try:
                    filing_to = datetime.date.fromisoformat(filing_to_str)
                    # Skip archives that are entirely after the cutoff – no data we need
                    # But don't skip archives that end after or around the cutoff
                    filing_from_str = archive.get("filingFrom", "")
                    if filing_from_str:
                        filing_from = datetime.date.fromisoformat(filing_from_str)
                        if filing_from > cutoff_date:
                            continue  # entire archive is after cutoff, skip
                except (ValueError, TypeError):
                    pass

            archive_url = f"https://data.sec.gov/submissions/{archive_name}"
            try:
                archive_raw = self._client.get_json(archive_url)
                archive_records = self._parse_filings(
                    {"filings": {"recent": archive_raw}},
                    cik, ticker, cutoff_date, allowed_forms,
                )
                records.extend(archive_records)
                logger.debug(
                    "Fetched %d more filings from archive %s for %s",
                    len(archive_records), archive_name, ticker,
                )
            except Exception as exc:
                logger.warning("Failed to fetch archive %s: %s", archive_name, exc)

        if not records:
            raise FilingNotFoundError(ticker, cutoff_date)

        # Sort descending by period_of_report
        records.sort(key=lambda r: r.period_of_report, reverse=True)

        logger.info(
            "FilingsIndex: found %d qualifying filings for %s (cik=%s, cutoff=%s)",
            len(records), ticker, cik, cutoff_date,
        )
        return records

    def _get_allowed_forms(self, period_type: FilingPeriodType) -> frozenset[str]:
        allowed = ALL_SUPPORTED_FORMS
        if period_type == FilingPeriodType.ANNUAL:
            allowed = ANNUAL_FORM_TYPES
        elif period_type == FilingPeriodType.QUARTERLY:
            allowed = QUARTERLY_FORM_TYPES

        if not self._config.allow_amendments:
            # Strip amendment variants
            allowed = frozenset(f for f in allowed if not f.endswith("/A"))

        return allowed

    def _parse_filings(
        self,
        raw: dict,
        cik: str,
        ticker: str,
        cutoff_date: datetime.date,
        allowed_forms: frozenset[str],
    ) -> list[FilingRecord]:
        """Parse the SEC submissions JSON and return qualifying FilingRecords."""
        recent = raw.get("filings", {}).get("recent", {})
        if not recent:
            # Sometimes archive files return data directly at root level
            recent = raw if "form" in raw else {}
        if not recent:
            logger.warning("No filings found in submissions for CIK=%s", cik)
            return []

        form_types: list[str] = recent.get("form", [])
        filing_dates: list[str] = recent.get("filingDate", [])
        # SEC API uses acceptanceDateTime (capital D and T)
        acceptance_datetimes: list[str] = (
            recent.get("acceptanceDateTime") or recent.get("acceptanceDatetime") or []
        )
        period_ends: list[str] = recent.get("reportDate", [])
        accessions: list[str] = recent.get("accessionNumber", [])

        records: list[FilingRecord] = []

        for i, form in enumerate(form_types):
            if form not in allowed_forms:
                continue

            try:
                acc_dt_str = acceptance_datetimes[i] if i < len(acceptance_datetimes) else ""
                acc_dt = parse_datetime(acc_dt_str) if acc_dt_str else None

                if acc_dt is None:
                    # Fall back to filing date
                    fd_str = filing_dates[i] if i < len(filing_dates) else ""
                    fd = parse_date(fd_str)
                    if fd is None:
                        continue
                    acc_dt = datetime.datetime.combine(fd, datetime.time(23, 59, 59))

                if not is_within_cutoff(acc_dt, cutoff_date):
                    continue  # This is the PIT gate

                period_str = period_ends[i] if i < len(period_ends) else ""
                period_end = parse_date(period_str)
                if period_end is None:
                    continue

                filing_date_str = filing_dates[i] if i < len(filing_dates) else ""
                filing_date = parse_date(filing_date_str) or period_end

                accession_raw = accessions[i] if i < len(accessions) else ""
                # Normalize: EDGAR returns '0001234567-23-000001'
                accession = accession_raw.replace("-", "").replace(" ", "")
                accession_formatted = (
                    f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"
                    if len(accession) == 18
                    else accession_raw
                )

                records.append(
                    FilingRecord(
                        cik=cik,
                        accession=accession_formatted,
                        form_type=form,
                        filing_date=filing_date,
                        acceptance_datetime=acc_dt,
                        period_of_report=period_end,
                        ticker=ticker,
                    )
                )
            except Exception as exc:
                logger.debug(
                    "Skipping filing index=%d for CIK=%s: %s", i, cik, exc
                )
                continue

        return records


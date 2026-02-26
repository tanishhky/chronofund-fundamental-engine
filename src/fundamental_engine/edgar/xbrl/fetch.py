"""
fetch.py – Fetches XBRL companyfacts from SEC EDGAR.

The companyfacts endpoint returns ALL historical XBRL data for a company
in a single JSON blob. We parse this into XBRLFact objects.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from fundamental_engine.constants import EDGAR_COMPANY_FACTS_URL, GAAP_NAMESPACES
from fundamental_engine.edgar.client import EdgarClient
from fundamental_engine.exceptions import XBRLParseError
from fundamental_engine.types import XBRLFact
from fundamental_engine.utils.dates import parse_date

logger = logging.getLogger(__name__)


class XBRLFetcher:
    """
    Fetches and parses the SEC companyfacts XBRL endpoint.

    Parameters
    ----------
    client:
        Configured EdgarClient instance.
    """

    def __init__(self, client: EdgarClient) -> None:
        self._client = client

    def fetch_all_facts(self, cik: str) -> dict[str, list[XBRLFact]]:
        """
        Fetch and parse all XBRL facts for a company.

        Returns a dict keyed by "{namespace}:{tag}" → list of XBRLFacts.

        Parameters
        ----------
        cik:
            Zero-padded 10-digit CIK.

        Returns
        -------
        dict[str, list[XBRLFact]]

        Raises
        ------
        XBRLParseError: on malformed response.
        """
        cik_int = int(cik)
        url = EDGAR_COMPANY_FACTS_URL.format(cik=cik_int)

        try:
            raw = self._client.get_json(url)
        except Exception as exc:
            raise XBRLParseError(cik, f"HTTP failure: {exc}") from exc

        facts_raw = raw.get("facts", {})
        result: dict[str, list[XBRLFact]] = {}

        for namespace in GAAP_NAMESPACES:
            ns_data = facts_raw.get(namespace, {})
            for tag, tag_data in ns_data.items():
                key = f"{namespace}:{tag}"
                units_data = tag_data.get("units", {})

                for unit, entries in units_data.items():
                    parsed = self._parse_entries(tag, namespace, unit, entries, cik)
                    if parsed:
                        existing = result.get(key, [])
                        existing.extend(parsed)
                        result[key] = existing

        total_facts = sum(len(v) for v in result.values())
        logger.info(
            "Fetched %d unique tags (%d total facts) for CIK=%s",
            len(result), total_facts, cik,
        )
        return result

    def _parse_entries(
        self,
        tag: str,
        namespace: str,
        unit: str,
        entries: list[dict[str, Any]],
        cik: str,
    ) -> list[XBRLFact]:
        """Parse a list of XBRL fact entries for a single tag/unit combination."""
        facts: list[XBRLFact] = []

        for entry in entries:
            try:
                val_raw = entry.get("val")
                if val_raw is None:
                    continue
                value = float(val_raw)

                end_str = entry.get("end", "")
                end_date = parse_date(end_str)
                if end_date is None:
                    continue

                start_str = entry.get("start")
                start_date = parse_date(start_str) if start_str else None

                filed_str = entry.get("filed", "")
                filed_date = parse_date(filed_str)
                if filed_date is None:
                    continue

                accession = str(entry.get("accn", ""))
                form = str(entry.get("form", ""))
                frame = entry.get("frame")

                facts.append(
                    XBRLFact(
                        tag=tag,
                        namespace=namespace,
                        value=value,
                        unit=unit,
                        start=start_date,
                        end=end_date,
                        accession=accession,
                        form=form,
                        frame=str(frame) if frame else None,
                        filed=filed_date,
                    )
                )
            except (ValueError, TypeError, KeyError) as exc:
                logger.debug("Skipping malformed fact tag=%s: %s", tag, exc)
                continue

        return facts

"""
cik_map.py – Ticker → CIK resolution using the SEC's company_tickers.json endpoint.

The mapping is cached to disk and refreshed only on explicit request.
CIKs are zero-padded to 10 digits as required by SEC API endpoints.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fundamental_engine.constants import EDGAR_TICKER_CIK_URL
from fundamental_engine.edgar.client import EdgarClient
from fundamental_engine.exceptions import CIKLookupError

logger = logging.getLogger(__name__)


class CIKMapper:
    """
    Resolves equity tickers to their SEC CIK numbers.

    Bulk downloads the SEC company_tickers.json (~1.5MB) and stores a
    normalized ticker→CIK mapping in memory. The raw JSON is cached to
    disk by EdgarClient automatically.

    Parameters
    ----------
    client:
        Configured EdgarClient instance.
    """

    def __init__(self, client: EdgarClient) -> None:
        self._client = client
        self._map: dict[str, str] = {}   # ticker (upper) → 10-digit CIK string
        self._name_map: dict[str, str] = {}  # ticker → company name

    def load(self) -> None:
        """
        Download and parse company_tickers.json from SEC.

        Safe to call multiple times; subsequent calls are no-ops if the
        internal map is already populated.
        """
        if self._map:
            return  # already loaded

        raw: dict[str, dict[str, object]] = self._client.get_json(EDGAR_TICKER_CIK_URL)

        # The JSON is a dict of integer index → {cik_str, ticker, title}
        for _idx, entry in raw.items():
            ticker = str(entry.get("ticker", "")).strip().upper()
            cik_raw = str(entry.get("cik_str", "")).strip()
            name = str(entry.get("title", "")).strip()

            if ticker and cik_raw:
                cik_padded = cik_raw.zfill(10)
                self._map[ticker] = cik_padded
                self._name_map[ticker] = name

        logger.info("CIK map loaded: %d entries", len(self._map))

    def resolve(self, ticker: str) -> str:
        """
        Resolve a ticker to a zero-padded 10-digit CIK string.

        Parameters
        ----------
        ticker:
            Equity ticker (case-insensitive).

        Returns
        -------
        str: 10-digit zero-padded CIK.

        Raises
        ------
        CIKLookupError: if the ticker is not found.
        """
        self.load()
        key = ticker.strip().upper()
        cik = self._map.get(key)
        if cik is None:
            raise CIKLookupError(ticker)
        return cik

    def resolve_many(self, tickers: list[str]) -> dict[str, str]:
        """
        Resolve multiple tickers at once.

        Parameters
        ----------
        tickers:
            List of equity tickers.

        Returns
        -------
        dict mapping ticker → CIK for successfully resolved tickers.
        Logs a warning for each unresolvable ticker rather than raising.
        """
        self.load()
        result: dict[str, str] = {}
        for t in tickers:
            try:
                result[t] = self.resolve(t)
            except CIKLookupError:
                logger.warning("Could not resolve ticker '%s' to CIK—skipping.", t)
        return result

    def company_name(self, ticker: str) -> str | None:
        """Return the SEC-registered company name for a ticker, or None."""
        self.load()
        return self._name_map.get(ticker.strip().upper())

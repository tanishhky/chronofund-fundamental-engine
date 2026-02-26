"""
segments_pdf.py – Parser for Bloomberg Segments PDF reports.

Bloomberg Segments PDFs provide geographic/product segment breakdowns.
This parser extracts segment-level revenue data and maps it to a
supplementary RawStatementTable for use in coverage analysis.
"""

from __future__ import annotations

import datetime
import logging
import re
from pathlib import Path
from typing import Any

import pdfplumber

from fundamental_engine.constants import BBG_SCALE_PATTERNS
from fundamental_engine.exceptions import BloombergParseError
from fundamental_engine.types import (
    BloombergColumn,
    DataSource,
    RawStatementTable,
    StatementType,
)

logger = logging.getLogger(__name__)
_YEAR_PATTERN = re.compile(r"(19|20)\d{2}")


class SegmentsPDFParser:
    """
    Parses Bloomberg Segments PDF reports.

    Segments data is output as StatementType.INCOME (revenue breakdown).
    Segment names become row labels; fiscal year columns become BloombergColumns.
    """

    def parse(
        self,
        path: Path,
        ticker: str,
        cutoff_date: datetime.date,
    ) -> RawStatementTable:
        """
        Parse a Bloomberg Segments PDF into a RawStatementTable.

        Parameters
        ----------
        path:
            Path to the PDF file.
        ticker:
            Equity ticker.
        cutoff_date:
            PIT cutoff date.

        Returns
        -------
        RawStatementTable with segment revenue rows.
        """
        if not path.exists():
            raise BloombergParseError(str(path), "File not found")

        scale = 1.0
        all_rows: list[list[str | None]] = []

        try:
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    for pattern, mult in BBG_SCALE_PATTERNS.items():
                        if pattern in text.lower():
                            scale = mult

                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            cleaned = [str(c).strip() if c else None for c in row]
                            if any(c for c in cleaned):
                                all_rows.append(cleaned)
        except Exception as exc:
            raise BloombergParseError(str(path), f"PDF read error: {exc}") from exc

        if not all_rows:
            raise BloombergParseError(str(path), "No data extracted from segment PDF")

        # Find header row
        header_idx = -1
        col_labels: list[str] = []
        for idx, row in enumerate(all_rows[:20]):
            labels = [str(c).strip() for c in row[1:] if c]
            year_like = [l for l in labels if _YEAR_PATTERN.search(l)]
            if len(year_like) >= 2:
                header_idx = idx
                col_labels = labels
                break

        if header_idx < 0:
            raise BloombergParseError(str(path), "No fiscal year header found in segment PDF")

        columns = [
            BloombergColumn(
                label=label,
                fiscal_year=int(m.group()) if (m := _YEAR_PATTERN.search(label)) else None,
                is_estimate=False,
                is_ltm=False,
                is_restated=False,
                period_end=(
                    datetime.date(int(_YEAR_PATTERN.search(label).group()), 12, 31)
                    if _YEAR_PATTERN.search(label)
                    else None
                ),
            )
            for label in col_labels
        ]

        data: dict[str, dict[str, Any]] = {}
        for row in all_rows[header_idx + 1 :]:
            if not row or not row[0]:
                continue
            segment_name = str(row[0]).strip()
            if not segment_name:
                continue
            vals: dict[str, Any] = {}
            for i, col in enumerate(columns):
                raw = row[i + 1] if (i + 1) < len(row) else None
                if raw:
                    clean = str(raw).replace(",", "").replace("(", "-").replace(")", "")
                    try:
                        vals[col.label] = float(clean)
                    except ValueError:
                        vals[col.label] = None
                else:
                    vals[col.label] = None
            data[f"Segment: {segment_name}"] = vals

        logger.info("Parsed %d segments from %s for %s", len(data), path.name, ticker)

        return RawStatementTable(
            ticker=ticker,
            statement_type=StatementType.INCOME,
            columns=columns,
            data=data,
            scale=scale,
            source=DataSource.BLOOMBERG_PDF,
        )

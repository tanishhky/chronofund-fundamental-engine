"""
statement_analysis_pdf.py – Parser for Bloomberg Financial Statement Analysis PDF.

Bloomberg's Statement Analysis PDFs contain multi-page tabular data with:
- Company header
- Scale indicator ("In Millions")
- Row labels in the leftmost column
- Fiscal year columns (with A/E/LTM suffixes)

Uses pdfplumber for table extraction and handles page-spanning tables.
"""

from __future__ import annotations

import datetime
import logging
import re
from pathlib import Path
from typing import Any

import pdfplumber

from fundamental_engine.constants import (
    BBG_ESTIMATE_KEYWORDS,
    BBG_LTM_KEYWORDS,
    BBG_SCALE_PATTERNS,
)
from fundamental_engine.exceptions import BloombergParseError
from fundamental_engine.types import (
    BloombergColumn,
    DataSource,
    RawStatementTable,
    StatementType,
)

logger = logging.getLogger(__name__)
_YEAR_PATTERN = re.compile(r"(19|20)\d{2}")


class StatementAnalysisPDFParser:
    """
    Parses Bloomberg Financial Statement Analysis PDF exports.

    Parameters
    ----------
    allow_ltm:
        Include LTM columns (default False).
    allow_estimates:
        Include estimate columns (default False, must be False for backtests).
    """

    def __init__(self, allow_ltm: bool = False, allow_estimates: bool = False) -> None:
        self._allow_ltm = allow_ltm
        self._allow_estimates = allow_estimates

    def parse(
        self,
        path: Path,
        ticker: str,
        cutoff_date: datetime.date,
        stmt_type: StatementType = StatementType.INCOME,
    ) -> RawStatementTable:
        """
        Parse a Bloomberg Statement Analysis PDF.

        Parameters
        ----------
        path:
            Path to the PDF file.
        ticker:
            Equity ticker.
        cutoff_date:
            PIT cutoff (columns after cutoff are filtered in the mapper).
        stmt_type:
            Type of financial statement in this PDF.

        Returns
        -------
        RawStatementTable

        Raises
        ------
        BloombergParseError: if extraction fails.
        """
        if not path.exists():
            raise BloombergParseError(str(path), "File not found")

        try:
            all_rows: list[list[str | None]] = []
            scale = 1.0

            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""

                    # Detect scale from text
                    for pattern, multiplier in BBG_SCALE_PATTERNS.items():
                        if pattern in page_text.lower():
                            scale = multiplier

                    # Extract tables from this page
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            cleaned = [
                                str(cell).strip() if cell else None for cell in row
                            ]
                            if any(cell for cell in cleaned):
                                all_rows.append(cleaned)

        except Exception as exc:
            raise BloombergParseError(str(path), f"PDF extraction error: {exc}") from exc

        if not all_rows:
            raise BloombergParseError(str(path), "No tables extracted from PDF")

        # Find header row
        header_idx, col_labels = self._find_header_row(all_rows)
        if header_idx < 0:
            raise BloombergParseError(str(path), "Could not identify column header row")

        columns = [self._parse_column(label, cutoff_date) for label in col_labels if label]

        # Parse data rows
        data: dict[str, dict[str, Any]] = {}
        for row in all_rows[header_idx + 1 :]:
            if not row or row[0] is None:
                continue
            row_label = str(row[0]).strip()
            if not row_label:
                continue
            row_vals: dict[str, Any] = {}
            for i, col in enumerate(columns):
                cell_idx = i + 1
                raw_val = row[cell_idx] if cell_idx < len(row) else None
                if raw_val:
                    # Clean numeric strings: remove commas and parentheses (negatives)
                    clean = raw_val.replace(",", "").replace("(", "-").replace(")", "")
                    try:
                        row_vals[col.label] = float(clean)
                    except ValueError:
                        row_vals[col.label] = None
                else:
                    row_vals[col.label] = None
            data[row_label] = row_vals

        return RawStatementTable(
            ticker=ticker,
            statement_type=stmt_type,
            columns=columns,
            data=data,
            scale=scale,
            source=DataSource.BLOOMBERG_PDF,
        )

    def _find_header_row(self, rows: list[list]) -> tuple[int, list[str]]:
        for idx, row in enumerate(rows[:15]):
            labels = [str(c).strip() for c in row[1:] if c]
            year_like = [l for l in labels if _YEAR_PATTERN.search(l)]
            if len(year_like) >= 2:
                return idx, labels
        return -1, []

    def _parse_column(self, label: str, cutoff_date: datetime.date) -> BloombergColumn:
        upper = label.upper()
        is_ltm = any(kw in upper for kw in BBG_LTM_KEYWORDS)
        is_estimate = not is_ltm and any(kw in upper for kw in BBG_ESTIMATE_KEYWORDS)
        is_restated = "RESTATED" in upper

        match = _YEAR_PATTERN.search(label)
        fiscal_year = int(match.group()) if match else None
        period_end = datetime.date(fiscal_year, 12, 31) if fiscal_year else None

        return BloombergColumn(
            label=label,
            fiscal_year=fiscal_year,
            is_estimate=is_estimate,
            is_ltm=is_ltm,
            is_restated=is_restated,
            period_end=period_end,
        )

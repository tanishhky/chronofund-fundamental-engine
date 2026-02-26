"""
constants.py – Immutable project-wide constants.
Do NOT modify these at runtime. Add new mapping entries here when extending coverage.
"""

from __future__ import annotations

# ── SEC EDGAR endpoints ──────────────────────────────────────────────────────
EDGAR_BASE_URL = "https://data.sec.gov"
EDGAR_SUBMISSIONS_URL = f"{EDGAR_BASE_URL}/submissions/CIK{{cik:010d}}.json"
EDGAR_COMPANY_FACTS_URL = f"{EDGAR_BASE_URL}/api/xbrl/companyfacts/CIK{{cik:010d}}.json"
EDGAR_FILING_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{filename}"
EDGAR_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"

# ── Supported filing types ───────────────────────────────────────────────────
ANNUAL_FORM_TYPES: frozenset[str] = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A"})
QUARTERLY_FORM_TYPES: frozenset[str] = frozenset({"10-Q", "10-Q/A"})
ALL_SUPPORTED_FORMS: frozenset[str] = ANNUAL_FORM_TYPES | QUARTERLY_FORM_TYPES

# ── GAAP taxonomy namespaces recognized ─────────────────────────────────────
GAAP_NAMESPACES: list[str] = [
    "us-gaap",
    "ifrs-full",
    "dei",
]

# ── Standard output column ordering ─────────────────────────────────────────
COMPANY_MASTER_COLS: list[str] = ["ticker", "cik", "company_name", "sic", "exchange"]

FILING_COLS: list[str] = [
    "ticker", "cik", "accession", "form_type", "filing_date",
    "acceptance_datetime", "period_of_report", "source",
]

INCOME_COLS: list[str] = [
    "ticker", "cik", "accession", "asof_date", "period_end", "source",
    "revenue", "cost_of_revenue", "gross_profit",
    "operating_expenses", "ebit", "ebitda",
    "interest_expense", "pretax_income",
    "income_tax_expense", "net_income",
    "eps_basic", "eps_diluted",
    "shares_basic", "shares_diluted",
]

BALANCE_COLS: list[str] = [
    "ticker", "cik", "accession", "asof_date", "period_end", "source",
    "cash_and_equivalents", "short_term_investments",
    "accounts_receivable", "inventory", "current_assets",
    "ppe_net", "goodwill", "intangibles", "total_assets",
    "accounts_payable", "short_term_debt", "current_liabilities",
    "long_term_debt", "total_liabilities",
    "common_equity", "retained_earnings", "total_equity",
]

CASHFLOW_COLS: list[str] = [
    "ticker", "cik", "accession", "asof_date", "period_end", "source",
    "cfo", "capex", "free_cash_flow",
    "cfi", "cff",
    "dividends_paid", "share_repurchases",
    "net_change_in_cash", "depreciation_amortization",
    "stock_based_compensation",
]

DERIVED_COLS: list[str] = [
    "ticker", "cik", "accession", "asof_date", "period_end", "source",
    "gross_margin", "ebit_margin", "net_margin",
    "roa", "roe", "roic",
    "current_ratio", "quick_ratio",
    "debt_to_equity", "net_debt",
    "fcf_yield",
]

# ── Accounting identity tolerance ────────────────────────────────────────────
# |Assets - (Liabilities + Equity)| / Assets < this threshold
BALANCE_SHEET_TOLERANCE: float = 0.01  # 1%

# ── Bloomberg column detection keywords ─────────────────────────────────────
BBG_ESTIMATE_KEYWORDS: frozenset[str] = frozenset({"E", "Est", "Estimate", "Proj", "Projected", "F"})
BBG_LTM_KEYWORDS: frozenset[str] = frozenset({"LTM", "TTM", "L12M"})
BBG_RESTATED_KEYWORD: str = "Restated"

# ── Scaling detection ────────────────────────────────────────────────────────
BBG_SCALE_PATTERNS: dict[str, float] = {
    "in millions": 1_000_000.0,
    "in billions": 1_000_000_000.0,
    "in thousands": 1_000.0,
}

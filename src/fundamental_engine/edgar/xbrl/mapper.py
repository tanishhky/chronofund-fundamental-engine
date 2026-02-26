"""
mapper.py – Maps XBRL GAAP tags to standardized field names.

The mapping is intentionally verbose and explicit. Each standardized field
has a list of acceptable GAAP tags, tried in priority order. Sign adjustments
are applied where necessary (e.g., capex is reported as negative in filings).

To extend: add new tag variants to TAG_PRIORITY_MAP below.
"""

from __future__ import annotations

from typing import NamedTuple


class TagMapping(NamedTuple):
    """
    Maps a standardized field to one or more XBRL tag candidates.

    Attributes
    ----------
    standard_field:
        Target column name in the standardized schema.
    tags:
        List of fully-qualified XBRL tags in priority order
        (e.g. 'us-gaap:Revenues').
    sign_flip:
        If True, multiply the raw value by -1 (for reported-negative items
        like CapEx and dividends paid).
    context_type:
        'duration' for income/cashflow items, 'instant' for balance sheet.
    """

    standard_field: str
    tags: list[str]
    sign_flip: bool
    context_type: str


# ── GAAP Tag Priority Map ─────────────────────────────────────────────────────
# Each entry = TagMapping(field, [preferred_tag, fallback1, fallback2, ...], sign_flip, ctx)
# Tags are tried in ORDER; first one found with valid data wins.

TAG_PRIORITY_MAP: list[TagMapping] = [

    # ── Income Statement ──────────────────────────────────────────────────────
    TagMapping(
        "revenue",
        [
            "us-gaap:Revenues",
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
            "us-gaap:SalesRevenueNet",
            "us-gaap:SalesRevenueGoodsNet",
            "us-gaap:RevenuesNetOfInterestExpense",
        ],
        False, "duration",
    ),
    TagMapping(
        "cost_of_revenue",
        [
            "us-gaap:CostOfRevenue",
            "us-gaap:CostOfGoodsAndServicesSold",
            "us-gaap:CostOfGoodsSold",
            "us-gaap:CostOfServices",
        ],
        False, "duration",
    ),
    TagMapping(
        "gross_profit",
        ["us-gaap:GrossProfit"],
        False, "duration",
    ),
    TagMapping(
        "operating_expenses",
        [
            "us-gaap:OperatingExpenses",
            "us-gaap:OperatingCostsAndExpenses",
        ],
        False, "duration",
    ),
    TagMapping(
        "ebit",
        [
            "us-gaap:OperatingIncomeLoss",
            "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        ],
        False, "duration",
    ),
    TagMapping(
        "ebitda",
        [
            "us-gaap:EarningsBeforeInterestTaxesDepreciationAmortization",
            "us-gaap:EBITDA",
        ],
        False, "duration",
    ),
    TagMapping(
        "interest_expense",
        [
            "us-gaap:InterestExpense",
            "us-gaap:InterestAndDebtExpense",
            "us-gaap:InterestExpenseDebt",
        ],
        False, "duration",
    ),
    TagMapping(
        "pretax_income",
        [
            "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ],
        False, "duration",
    ),
    TagMapping(
        "income_tax_expense",
        [
            "us-gaap:IncomeTaxExpenseBenefit",
        ],
        False, "duration",
    ),
    TagMapping(
        "net_income",
        [
            "us-gaap:NetIncomeLoss",
            "us-gaap:ProfitLoss",
            "us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic",
        ],
        False, "duration",
    ),
    TagMapping(
        "eps_basic",
        [
            "us-gaap:EarningsPerShareBasic",
        ],
        False, "duration",
    ),
    TagMapping(
        "eps_diluted",
        [
            "us-gaap:EarningsPerShareDiluted",
        ],
        False, "duration",
    ),
    TagMapping(
        "shares_basic",
        [
            "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic",
        ],
        False, "duration",
    ),
    TagMapping(
        "shares_diluted",
        [
            "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
        ],
        False, "duration",
    ),

    # ── Balance Sheet ─────────────────────────────────────────────────────────
    TagMapping(
        "cash_and_equivalents",
        [
            "us-gaap:CashAndCashEquivalentsAtCarryingValue",
            "us-gaap:Cash",
            "us-gaap:CashCashEquivalentsAndShortTermInvestments",
        ],
        False, "instant",
    ),
    TagMapping(
        "short_term_investments",
        [
            "us-gaap:ShortTermInvestments",
            "us-gaap:MarketableSecuritiesCurrent",
        ],
        False, "instant",
    ),
    TagMapping(
        "accounts_receivable",
        [
            "us-gaap:AccountsReceivableNetCurrent",
            "us-gaap:ReceivablesNetCurrent",
        ],
        False, "instant",
    ),
    TagMapping(
        "inventory",
        [
            "us-gaap:InventoryNet",
            "us-gaap:Inventories",
        ],
        False, "instant",
    ),
    TagMapping(
        "current_assets",
        ["us-gaap:AssetsCurrent"],
        False, "instant",
    ),
    TagMapping(
        "ppe_net",
        [
            "us-gaap:PropertyPlantAndEquipmentNet",
            "us-gaap:PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
        ],
        False, "instant",
    ),
    TagMapping(
        "goodwill",
        ["us-gaap:Goodwill"],
        False, "instant",
    ),
    TagMapping(
        "intangibles",
        [
            "us-gaap:IntangibleAssetsNetExcludingGoodwill",
            "us-gaap:FiniteLivedIntangibleAssetsNet",
        ],
        False, "instant",
    ),
    TagMapping(
        "total_assets",
        ["us-gaap:Assets"],
        False, "instant",
    ),
    TagMapping(
        "accounts_payable",
        [
            "us-gaap:AccountsPayableCurrent",
            "us-gaap:AccountsPayableAndAccruedLiabilitiesCurrent",
        ],
        False, "instant",
    ),
    TagMapping(
        "short_term_debt",
        [
            "us-gaap:LongTermDebtCurrent",
            "us-gaap:ShortTermBorrowings",
            "us-gaap:DebtCurrent",
        ],
        False, "instant",
    ),
    TagMapping(
        "current_liabilities",
        ["us-gaap:LiabilitiesCurrent"],
        False, "instant",
    ),
    TagMapping(
        "long_term_debt",
        [
            "us-gaap:LongTermDebtNoncurrent",
            "us-gaap:LongTermDebt",
            "us-gaap:LongTermDebtAndCapitalLeaseObligations",
        ],
        False, "instant",
    ),
    TagMapping(
        "total_liabilities",
        ["us-gaap:Liabilities"],
        False, "instant",
    ),
    TagMapping(
        "common_equity",
        [
            "us-gaap:StockholdersEquity",
            "us-gaap:CommonStockholdersEquity",
        ],
        False, "instant",
    ),
    TagMapping(
        "retained_earnings",
        [
            "us-gaap:RetainedEarningsAccumulatedDeficit",
        ],
        False, "instant",
    ),
    TagMapping(
        "total_equity",
        [
            "us-gaap:StockholdersEquity",
            "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ],
        False, "instant",
    ),

    # ── Cash Flow Statement ───────────────────────────────────────────────────
    TagMapping(
        "cfo",
        [
            "us-gaap:NetCashProvidedByUsedInOperatingActivities",
            "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ],
        False, "duration",
    ),
    TagMapping(
        "capex",
        [
            "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
            "us-gaap:PaymentsForCapitalImprovements",
            "us-gaap:CapitalExpendituresIncurredButNotYetPaid",
        ],
        True,  # sign_flip: reported negative in filings, we store positive
        "duration",
    ),
    TagMapping(
        "cfi",
        [
            "us-gaap:NetCashProvidedByUsedInInvestingActivities",
            "us-gaap:NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
        ],
        False, "duration",
    ),
    TagMapping(
        "cff",
        [
            "us-gaap:NetCashProvidedByUsedInFinancingActivities",
            "us-gaap:NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
        ],
        False, "duration",
    ),
    TagMapping(
        "dividends_paid",
        [
            "us-gaap:PaymentsOfDividends",
            "us-gaap:PaymentsOfDividendsCommonStock",
        ],
        True,  # sign_flip
        "duration",
    ),
    TagMapping(
        "share_repurchases",
        [
            "us-gaap:PaymentsForRepurchaseOfCommonStock",
        ],
        True,  # sign_flip
        "duration",
    ),
    TagMapping(
        "net_change_in_cash",
        [
            "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            "us-gaap:CashAndCashEquivalentsPeriodIncreaseDecrease",
            "us-gaap:NetCashProvidedByUsedInContinuingOperations",
        ],
        False, "duration",
    ),
    TagMapping(
        "depreciation_amortization",
        [
            "us-gaap:DepreciationDepletionAndAmortization",
            "us-gaap:DepreciationAndAmortization",
            "us-gaap:Depreciation",
        ],
        False, "duration",
    ),
    TagMapping(
        "stock_based_compensation",
        [
            "us-gaap:ShareBasedCompensation",
            "us-gaap:AllocatedShareBasedCompensationExpense",
        ],
        False, "duration",
    ),
]

# Build lookup index: standard_field → TagMapping
FIELD_TO_MAPPING: dict[str, TagMapping] = {m.standard_field: m for m in TAG_PRIORITY_MAP}

# Build reverse index: xbrl_tag → (standard_field, sign_flip, context_type)
TAG_TO_FIELD: dict[str, tuple[str, bool, str]] = {}
for mapping in TAG_PRIORITY_MAP:
    for tag in mapping.tags:
        # Only register the first (highest priority) occurrence
        if tag not in TAG_TO_FIELD:
            TAG_TO_FIELD[tag] = (mapping.standard_field, mapping.sign_flip, mapping.context_type)

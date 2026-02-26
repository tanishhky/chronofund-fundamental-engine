# Fundamental Engine

> **Point-in-Time Fundamental Data Engine for Equity Research**
> SEC EDGAR + Bloomberg · Production-Ready · Survivorship-Bias Aware

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│                        CLI / API                           │
│          edgar_pull                 bbg_ingest             │
└──────────────────┬─────────────────────┬───────────────────┘
                   │                     │
        ┌──────────▼──────────┐ ┌───────▼────────────┐
        │   Snapshot Builder  │ │  Bloomberg Ingest  │
        │  snapshot/builder   │ │  bloomberg/ingest  │
        └──────────┬──────────┘ └───────┬────────────┘
                   │                     │
        ┌──────────▼──────────┐ ┌───────▼────────────┐
        │   EDGAR Module      │ │  Bloomberg Parsers │
        │  edgar/client       │ │  xlsx_generic      │
        │  edgar/cik_map      │ │  statement_pdf     │
        │  edgar/filings_idx  │ │  segments_pdf      │
        │  edgar/xbrl/*       │ └───────┬────────────┘
        └──────────┬──────────┘         │
                   │                     │
        ┌──────────▼─────────────────────▼────────────┐
        │           Data Layer (Unified Schema)        │
        │    data/schema · data/validation · outputs  │
        └──────────────────────────────────────────────┘
                   │
        ┌──────────▼──────────────────────────────────┐
        │             Output Tables                   │
        │  company_master   filings                   │
        │  statements_income    statements_balance    │
        │  statements_cashflow  derived_metrics       │
        └─────────────────────────────────────────────┘
```

---

## Point-in-Time Logic

**No lookahead bias** is enforced at multiple levels:

| Layer | Mechanism |
|---|---|
| `FilingsIndex` | Primary gate: `acceptance_datetime ≤ end-of-cutoff-day` |
| `FilingSelector` | Secondary assertion: raises `CutoffViolationError` if any filing slips through |
| `XBRLParser` | Passes `cutoff_date` to every `select_best_fact_for_period()` call to exclude facts filed after cutoff |
| `BloombergMapper` | Skips columns whose `period_end > cutoff_date` |
| `SnapshotRequest` | `allow_estimates=False` and `allow_ltm=False` by default |

### Why This Matters

A filing for fiscal year 2016 is typically filed in February or March 2017. If your backtest cutoff is `2016-12-31`, that filing is **not available** to an investor on that date. The engine uses `acceptance_datetime` (the precise SEC filing acceptance timestamp) — not `filing_date` or `period_end` — as the availability gate.

```
  Fiscal Year End      Filing Accepted     Restatement
  ─────────────────────────────────────────────────────────▶ time
  2016-12-31           2017-02-15          2017-11-01

  Cutoff: 2016-12-31   → Filing NOT available (accepted in Feb 2017)
  Cutoff: 2017-03-01   → Filing available (accepted Feb 15)
  Cutoff: 2017-12-31   → Restated data NOT available (filed Nov 2017)
```

---

## Survivorship Bias Prevention

The engine does **not** constrain the universe to companies that survived. To prevent survivorship bias in downstream systems:

1. **No ticker filtering** — All tickers in the request are attempted. Missing tickers are logged in the `CoverageReport`, not silently dropped.
2. **`CoverageReport` tracks all failures** — Downstream backtest systems can use `missing_tickers` to identify delisted or merged companies.
3. **Historical CIK map** — SEC's `company_tickers.json` includes both active and historical companies.
4. **No forward-fill** — Missing data is `NaN`, not forward-filled from future periods.

When integrating with a backtest system, the recommended pattern is:
```python
# Read coverage report to flag delisted/missing companies
report = result.coverage_report
# Assign zero weight (or flag as 'data unavailable') for missing tickers
# rather than filtering them out of the universe entirely
```

---

## Quick Start

### Installation

```bash
cd fundamental-engine
pip install -e ".[dev]"
```

### Environment Setup

```bash
cp .env.example .env
# Edit .env and set SEC_USER_AGENT:
# SEC_USER_AGENT="YourName/1.0 your@email.com"
```

### Pull EDGAR Snapshot

```bash
edgar_pull \
  --tickers tickers.csv \
  --cutoff 2016-12-31 \
  --out out/ \
  --user-agent "Research/1.0 me@example.com"
```

`tickers.csv` format:
```
ticker
AAPL
MSFT
GOOGL
```

### Ingest Bloomberg XLSX

```bash
bbg_ingest \
  --file bloomberg_export.xlsx \
  --ticker AAPL \
  --cutoff 2016-12-31 \
  --out out/
```

### Python API

```python
import datetime
from fundamental_engine.config import EngineConfig
from fundamental_engine.snapshot.builder import build_edgar_snapshot
from fundamental_engine.types import SnapshotRequest, FilingPeriodType

config = EngineConfig(user_agent="MyProject/1.0 me@example.com")

request = SnapshotRequest(
    tickers=["AAPL", "MSFT"],
    cutoff_date=datetime.date(2016, 12, 31),
    period_type=FilingPeriodType.ANNUAL,
    allow_estimates=False,  # ALWAYS False for backtests
    allow_ltm=False,
)

result = build_edgar_snapshot(request, config=config)
income_df = result.tables["statements_income"]
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Extending the GAAP Tag Mapping

To add coverage for a new GAAP tag (e.g., a new SEC standard):

1. Open `src/fundamental_engine/edgar/xbrl/mapper.py`
2. Find the `TagMapping` for the relevant standard field (e.g., `"revenue"`)
3. Append your new tag to its `tags` list
4. Tags are tried **in order** — add new variants at the end to avoid disrupting existing priority

```python
# Example: Add a new revenue tag
TagMapping(
    "revenue",
    [
        "us-gaap:Revenues",                        # Highest priority
        "us-gaap:RevenueFromContractWithCustomer", # Existing fallback
        "us-gaap:MyNewRevenueTag",                 # Add new variant here
    ],
    False, "duration",
),
```

---

## Integration with Valuation Engine

The `SnapshotResult` object is the handoff point. To integrate:

```python
from fundamental_engine.types import SnapshotResult

def value_company(snapshot: SnapshotResult, ticker: str) -> float:
    income = snapshot.tables["statements_income"]
    balance = snapshot.tables["statements_balance"]
    cf = snapshot.tables["statements_cashflow"]
    derived = snapshot.tables["derived_metrics"]

    ticker_income = income[income["ticker"] == ticker].sort_values("period_end")
    # ... compute DCF, EV/EBITDA, etc.
```

**Key contract**: all data in `SnapshotResult.tables` is guaranteed to have `asof_date ≤ snapshot.cutoff`. No further PIT checks are needed in downstream systems.

---

## Project Structure

```
fundamental-engine/
  src/fundamental_engine/
    config.py            # Immutable EngineConfig (frozen dataclass)
    constants.py         # SEC endpoints, column names, GAAP namespaces
    types.py             # SnapshotRequest, SnapshotResult, XBRLFact, etc.
    exceptions.py        # CutoffViolationError, FilingNotFoundError, etc.

    utils/
      dates.py           # is_within_cutoff() — primary PIT gate
      rate_limit.py      # Token bucket SEC rate limiter (max 10 RPS)
      retry.py           # Exponential backoff decorator
      io.py              # ResponseCache (diskcache), Parquet/CSV I/O
      logging.py         # Structured logging factory

    data/
      schema.py          # SchemaDefinition for all 6 output tables
      validation.py      # Balance sheet identity, cashflow reconciliation
      outputs.py         # write_snapshot()

    edgar/
      client.py          # SEC HTTP client with caching
      cik_map.py         # Ticker → CIK resolution
      filings_index.py   # Filing list with PIT filtering
      xbrl/
        fetch.py         # companyfacts endpoint → XBRLFact objects
        contexts.py      # Context selection (consolidated, annual, cutoff)
        mapper.py        # GAAP tag → standard field priority map
        parser.py        # Assembles row dicts from XBRLFact objects

    bloomberg/
      ingest.py          # build_bloomberg_snapshot_from_xlsx()
      mapping.py         # Bloomberg label → standard field mapping
      parsers/
        xlsx_generic.py  # XLSX workbook parser
        statement_analysis_pdf.py  # PDF table parser
        segments_pdf.py  # Segment breakdown PDF parser

    snapshot/
      builder.py         # build_edgar_snapshot() orchestrator
      selector.py        # Best filing selection per period
      coverage.py        # CoverageReport generation

    cli/main.py          # edgar_pull, bbg_ingest commands

  tests/                 # pytest unit tests
  examples/              # Runnable example scripts
```

---

## Design Decisions

| Decision | Rationale |
|---|---|
| `acceptance_datetime` as PIT gate | More precise than `filing_date`; SEC timestamps to the second |
| Frozen `EngineConfig` dataclass | Prevents accidental mutation of global state |
| `diskcache` for HTTP responses | Cross-session caching; EDGAR historical data is immutable |
| Token bucket rate limiter | Smooth distribution of requests vs. burst then wait |
| Parquet as default output | Typed, compressed, fast; compatible with pandas, polars, Arrow |
| `NaN` for missing data | Downstream systems must explicitly handle gaps; no silent forward-fill |
| Secondary `CutoffViolationError` in selector | Defense-in-depth; ensures lookahead bias cannot slip through even if upstream logic has a bug |

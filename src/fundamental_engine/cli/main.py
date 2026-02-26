"""
main.py – CLI entry points for the fundamental engine.

Commands:
  edgar_pull   Pull EDGAR snapshots for a list of tickers.
  bbg_ingest   Ingest a Bloomberg XLSX export.

Usage:
  edgar_pull --tickers tickers.csv --cutoff 2016-12-31 --out out/ --user-agent "Proj/1.0 a@b.com"
  bbg_ingest --file bloomberg.xlsx --cutoff 2016-12-31 --out out/ --ticker AAPL
"""

from __future__ import annotations

import csv
import datetime
import sys
from pathlib import Path

import click

from fundamental_engine.bloomberg.ingest import build_bloomberg_snapshot_from_xlsx
from fundamental_engine.config import EngineConfig
from fundamental_engine.data.outputs import write_snapshot
from fundamental_engine.snapshot.builder import build_edgar_snapshot
from fundamental_engine.types import FilingPeriodType, SnapshotRequest
from fundamental_engine.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


# ── Shared options ────────────────────────────────────────────────────────────

def _parse_cutoff(ctx: click.Context, param: click.Parameter, value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise click.BadParameter(f"Expected YYYY-MM-DD, got: {value!r}")


# ── edgar_pull ─────────────────────────────────────────────────────────────────

@click.command("edgar_pull")
@click.option(
    "--tickers",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a CSV file with a 'ticker' column.",
)
@click.option(
    "--cutoff",
    required=True,
    callback=_parse_cutoff,
    is_eager=True,
    help="Point-in-time cutoff date (YYYY-MM-DD).",
)
@click.option(
    "--out",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory.",
)
@click.option(
    "--user-agent",
    required=True,
    envvar="SEC_USER_AGENT",
    help='SEC User-Agent header. Format: "Name/1.0 email@example.com"',
)
@click.option(
    "--fmt",
    default="parquet",
    type=click.Choice(["parquet", "csv"]),
    show_default=True,
    help="Output file format.",
)
@click.option(
    "--period",
    default="annual",
    type=click.Choice(["annual", "quarterly"]),
    show_default=True,
    help="Fiscal period type.",
)
@click.option(
    "--allow-amendments/--no-allow-amendments",
    default=True,
    show_default=True,
    help="Prefer 10-K/A amended filings.",
)
@click.option("--log-level", default="INFO", show_default=True)
def edgar_pull(
    tickers: Path,
    cutoff: datetime.date,
    out: Path,
    user_agent: str,
    fmt: str,
    period: str,
    allow_amendments: bool,
    log_level: str,
) -> None:
    """Pull point-in-time EDGAR fundamental data for a list of tickers."""
    configure_logging(log_level)

    ticker_list = _load_tickers(tickers)
    if not ticker_list:
        click.echo("ERROR: No tickers found in the provided CSV.", err=True)
        sys.exit(1)

    click.echo(
        f"edgar_pull: {len(ticker_list)} tickers | cutoff={cutoff} | fmt={fmt}"
    )

    config = EngineConfig(
        user_agent=user_agent,
        output_dir=out,
        allow_amendments=allow_amendments,
        log_level=log_level,
    )

    request = SnapshotRequest(
        tickers=ticker_list,
        cutoff_date=cutoff,
        period_type=FilingPeriodType.ANNUAL if period == "annual" else FilingPeriodType.QUARTERLY,
        allow_estimates=False,
        allow_ltm=False,
    )

    result = build_edgar_snapshot(request, config=config)
    paths = write_snapshot(result, out, fmt=fmt, validate=True)

    click.echo(f"\nSnapshot written to: {out}/{cutoff}/")
    for table, path in paths.items():
        click.echo(f"  {table}: {path.name}")

    report = result.coverage_report
    click.echo(
        f"\nCoverage: {len(report.found_tickers)}/{report.total_tickers} tickers "
        f"({report.coverage_ratio:.1%})"
    )
    if report.missing_tickers:
        click.echo(f"  Missing: {', '.join(report.missing_tickers[:10])}")


# ── bbg_ingest ────────────────────────────────────────────────────────────────

@click.command("bbg_ingest")
@click.option(
    "--file",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to Bloomberg XLSX export.",
)
@click.option(
    "--cutoff",
    required=True,
    callback=_parse_cutoff,
    is_eager=True,
    help="Point-in-time cutoff date (YYYY-MM-DD).",
)
@click.option(
    "--ticker",
    required=True,
    help="Ticker symbol to associate with this Bloomberg file.",
)
@click.option(
    "--out",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory.",
)
@click.option("--fmt", default="parquet", type=click.Choice(["parquet", "csv"]))
@click.option("--log-level", default="INFO", show_default=True)
def bbg_ingest(
    file: Path,
    cutoff: datetime.date,
    ticker: str,
    out: Path,
    fmt: str,
    log_level: str,
) -> None:
    """Ingest a Bloomberg XLSX financial statement export."""
    configure_logging(log_level)
    click.echo(f"bbg_ingest: {file} | ticker={ticker} | cutoff={cutoff}")

    config = EngineConfig(output_dir=out)
    result = build_bloomberg_snapshot_from_xlsx(
        path=file, cutoff_date=cutoff, ticker=ticker, config=config
    )

    paths = write_snapshot(result, out, fmt=fmt, validate=True)
    click.echo(f"\nSnapshot written to: {out}/{cutoff}/")
    for table, path in paths.items():
        click.echo(f"  {table}: {path.name}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_tickers(csv_path: Path) -> list[str]:
    """Load ticker symbols from a CSV file with a 'ticker' column."""
    tickers: list[str] = []
    with csv_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return []
        col = next(
            (c for c in reader.fieldnames if c.lower() == "ticker"),
            reader.fieldnames[0] if reader.fieldnames else None,
        )
        if col is None:
            return []
        for row in reader:
            val = row.get(col, "").strip().upper()
            if val:
                tickers.append(val)
    return tickers


if __name__ == "__main__":
    # Allow running individual commands: python -m fundamental_engine.cli.main
    edgar_pull()

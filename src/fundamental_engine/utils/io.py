"""
io.py – File I/O helpers for reading/writing DataFrames and caching.

Supports Parquet (preferred) and CSV output. Caching uses diskcache
to persist HTTP responses and parsed XBRL blobs across sessions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import diskcache
import pandas as pd

logger = logging.getLogger(__name__)


# ── DataFrame I/O ─────────────────────────────────────────────────────────────

def write_dataframe(
    df: pd.DataFrame,
    output_dir: Path,
    table_name: str,
    fmt: str = "parquet",
) -> Path:
    """
    Write a DataFrame to disk in the specified format.

    Parameters
    ----------
    df:
        DataFrame to write.
    output_dir:
        Directory to write into (created if necessary).
    table_name:
        Filename stem (e.g. 'statements_income').
    fmt:
        'parquet' or 'csv'.

    Returns
    -------
    Path to the written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "parquet":
        path = output_dir / f"{table_name}.parquet"
        df.to_parquet(path, index=False, engine="pyarrow")
    elif fmt == "csv":
        path = output_dir / f"{table_name}.csv"
        df.to_csv(path, index=False)
    else:
        raise ValueError(f"Unsupported output format: {fmt!r}")
    logger.debug("Wrote %d rows → %s", len(df), path)
    return path


def read_dataframe(path: Path) -> pd.DataFrame:
    """
    Read a DataFrame from disk. Auto-detects Parquet vs CSV.

    Parameters
    ----------
    path:
        File path to read.

    Returns
    -------
    pd.DataFrame
    """
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path, engine="pyarrow")
    elif suffix == ".csv":
        return pd.read_csv(path, low_memory=False)
    else:
        raise ValueError(f"Unsupported file type: {suffix!r}")


def write_json(obj: Any, path: Path) -> None:
    """Write a JSON-serializable object to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=str)


def read_json(path: Path) -> Any:
    """Read a JSON file and return the parsed object."""
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ── Disk-based HTTP cache ─────────────────────────────────────────────────────

class ResponseCache:
    """
    Disk-backed cache for HTTP responses and parsed JSON blobs.

    Uses `diskcache.Cache` behind the scenes for cross-session persistence.

    Parameters
    ----------
    cache_dir:
        Root directory for cache data.
    size_limit_gb:
        Maximum cache size in gigabytes.
    """

    def __init__(self, cache_dir: Path, size_limit_gb: float = 5.0) -> None:
        self._cache = diskcache.Cache(
            str(cache_dir),
            size_limit=int(size_limit_gb * 1024 ** 3),
        )

    def get(self, key: str) -> Any | None:
        """Return cached value or None."""
        return self._cache.get(key)

    def set(self, key: str, value: Any, expire: int | None = None) -> None:
        """
        Store value under key.

        Parameters
        ----------
        key:
            Cache key.
        value:
            Serializable value to store.
        expire:
            TTL in seconds. None = no expiry.
        """
        self._cache.set(key, value, expire=expire)

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def close(self) -> None:
        """Close the underlying cache file handles."""
        self._cache.close()

    def __enter__(self) -> "ResponseCache":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

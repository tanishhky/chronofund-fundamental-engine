"""
hashing.py – Content-based cache key generation.
Used to cache downloaded XBRL/filing files without relying on mutable paths.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def dict_hash(obj: dict[str, Any]) -> str:
    """
    Compute a stable SHA-256 hex digest for a JSON-serializable dict.
    Keys are sorted for determinism.

    Parameters
    ----------
    obj:
        A JSON-serializable dictionary.

    Returns
    -------
    str (64-char hex)
    """
    canonical = json.dumps(obj, sort_keys=True, default=str)
    return sha256_hex(canonical.encode("utf-8"))


def request_cache_key(url: str, params: dict[str, Any] | None = None) -> str:
    """
    Generate a stable cache key for an HTTP request.

    Parameters
    ----------
    url:
        The request URL.
    params:
        Optional query parameters dict.

    Returns
    -------
    str (64-char hex)
    """
    payload: dict[str, Any] = {"url": url}
    if params:
        payload["params"] = params
    return dict_hash(payload)


def accession_cache_key(cik: str, accession: str, filename: str) -> str:
    """
    Generate a cache key for a specific filing document.

    Parameters
    ----------
    cik:
        SEC CIK (zero-padded 10 digits).
    accession:
        Accession number (with dashes).
    filename:
        The specific file within the filing archive.
    """
    return dict_hash({"cik": cik, "accession": accession, "filename": filename})

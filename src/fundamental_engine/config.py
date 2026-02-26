"""
config.py – Central configuration using environment variables and/or explicit overrides.
All settings are immutable after construction (frozen dataclass).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class EngineConfig:
    """
    Immutable engine configuration.

    Parameters
    ----------
    user_agent:
        HTTP header value required by SEC EDGAR. Format: "Name/Version email".
    cache_dir:
        Directory for caching downloaded SEC filings and CIK maps.
    output_dir:
        Default output directory for snapshots.
    sec_rate_limit_rps:
        Maximum requests per second to SEC EDGAR (default 8, max 10).
    allow_amendments:
        If True, prefer 10-K/A and 10-Q/A amendments over original filings.
    allow_ltm:
        If True, allow LTM (last twelve months) columns in Bloomberg data.
    allow_estimates:
        If True, allow estimate columns in Bloomberg data.
        MUST remain False for point-in-time research.
    log_level:
        Python logging level string.
    """

    user_agent: str = field(
        default_factory=lambda: os.getenv("SEC_USER_AGENT", "ResearchProject/1.0 researcher@example.com")
    )
    cache_dir: Path = field(
        default_factory=lambda: Path(os.getenv("CACHE_DIR", ".cache"))
    )
    output_dir: Path = field(
        default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "out"))
    )
    sec_rate_limit_rps: float = field(
        default_factory=lambda: float(os.getenv("SEC_RATE_LIMIT_RPS", "8"))
    )
    allow_amendments: bool = True
    allow_ltm: bool = False
    allow_estimates: bool = False
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )

    def __post_init__(self) -> None:
        if not self.user_agent or " " not in self.user_agent:
            raise ValueError(
                "SEC_USER_AGENT must be set and follow format: 'Name/Version email'"
            )
        if self.sec_rate_limit_rps > 10:
            raise ValueError("SEC rate limit cannot exceed 10 RPS (SEC policy).")

    @classmethod
    def from_env(cls) -> "EngineConfig":
        """Construct config entirely from environment variables."""
        return cls(
            allow_amendments=os.getenv("ALLOW_AMENDMENTS", "true").lower() == "true",
            allow_ltm=os.getenv("ALLOW_LTM", "false").lower() == "true",
            allow_estimates=os.getenv("ALLOW_ESTIMATES", "false").lower() == "true",
        )

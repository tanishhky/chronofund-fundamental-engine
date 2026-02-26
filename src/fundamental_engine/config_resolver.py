"""
config_resolver.py – Unified precedence for SnapshotRequest vs EngineConfig.

Rule: SnapshotRequest fields always override EngineConfig defaults.
      This applies to: allow_amendments, allow_ltm, allow_estimates.

Use ``resolve_config(request, config)`` to get a single ``ResolvedConfig``
object that all downstream components (FilingSelector, BloombergMapper, etc.)
consume. Never read from request and config separately in business logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from fundamental_engine.config import EngineConfig
from fundamental_engine.types import SnapshotRequest


@dataclass(frozen=True)
class ResolvedConfig:
    """
    Merged view of EngineConfig + SnapshotRequest with clear precedence.

    SnapshotRequest wins on every field it carries; EngineConfig
    supplies defaults for fields not present in the request.

    Attributes
    ----------
    allow_amendments:
        Prefer 10-K/A over 10-K originals.
    allow_ltm:
        Include LTM/TTM columns (must be False for backtests).
    allow_estimates:
        Include forward estimate columns (must be False for backtests).
    user_agent:
        SEC User-Agent string (always from EngineConfig; not overridable per-request).
    """

    allow_amendments: bool
    allow_ltm: bool
    allow_estimates: bool
    user_agent: str

    def assert_pit_safe(self) -> None:
        """
        Raise ValueError if configuration permits data that could cause
        lookahead bias in a backtest context.

        Call this at the top of any build function to catch misconfiguration early.
        """
        if self.allow_estimates:
            raise ValueError(
                "allow_estimates=True is not permitted in point-in-time backtests. "
                "Estimate columns contain forward-looking data. "
                "Set allow_estimates=False on your SnapshotRequest."
            )


def resolve_config(
    request: SnapshotRequest,
    config: EngineConfig,
) -> ResolvedConfig:
    """
    Merge SnapshotRequest overrides on top of EngineConfig defaults.

    Precedence: SnapshotRequest > EngineConfig.

    Parameters
    ----------
    request:
        The per-call snapshot request.
    config:
        The engine-wide configuration.

    Returns
    -------
    ResolvedConfig with one authoritative value per flag.
    """
    return ResolvedConfig(
        # SnapshotRequest.include_amendments maps to EngineConfig.allow_amendments
        allow_amendments=request.include_amendments,
        # allow_ltm and allow_estimates: request is authoritative
        allow_ltm=request.allow_ltm,
        allow_estimates=request.allow_estimates,
        # user_agent cannot be overridden per-request (it's a credentials concern)
        user_agent=config.user_agent,
    )

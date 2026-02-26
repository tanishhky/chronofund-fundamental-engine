"""
Fundamental Engine
==================
Point-in-time fundamental data engine for equity research.
Supports SEC EDGAR and Bloomberg data sources.
"""

from fundamental_engine.config import EngineConfig
from fundamental_engine.exceptions import (
    CutoffViolationError,
    FilingNotFoundError,
    SchemaValidationError,
    XBRLParseError,
)

__version__ = "0.1.0"
__all__ = [
    "EngineConfig",
    "CutoffViolationError",
    "FilingNotFoundError",
    "SchemaValidationError",
    "XBRLParseError",
]

"""Shared exception types for Noxus.

Kept dependency-free so any layer (the deterministic patch engine, the JSON/agent
parsing layer, the orchestrator) can raise/catch the same fail-safe error without
coupling to higher-level modules.
"""

from __future__ import annotations

from typing import Optional


class SchemaContractError(Exception):
    """Raised when an LLM output cannot be parsed/validated after one repair.

    ``raw_excerpt`` carries a short, sanitized snippet of the offending model
    output for diagnostics. It never contains an API key or Authorization header.
    """

    def __init__(self, message: str, *, raw_excerpt: Optional[str] = None) -> None:
        super().__init__(message)
        self.raw_excerpt = raw_excerpt

"""Loading and schema validation for the security policy and text inputs.

All loading is local file I/O only. No network, no cloud.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .schemas import SecurityPolicy


def load_text_file(path: str | Path) -> str:
    """Load a UTF-8 text file (system prompt, business context, etc.)."""
    return Path(path).read_text(encoding="utf-8")


def load_yaml_policy(path: str | Path) -> dict[str, Any]:
    """Load the raw security policy YAML into a plain dict (unvalidated)."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"Security policy must be a YAML mapping, got {type(raw).__name__}."
        )
    return raw


def validate_policy(raw_yaml: dict[str, Any]) -> SecurityPolicy:
    """Validate a raw policy dict against the strict SecurityPolicy schema.

    Raises pydantic.ValidationError on a malformed policy.
    """
    return SecurityPolicy.model_validate(raw_yaml)

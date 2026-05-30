"""Strict JSON schema contracts with a single bounded repair attempt.

The flow is: parse a JSON object -> validate against a Pydantic schema. On any
failure, exactly ONE repair attempt is made via the provider. If that still
fails, a SchemaContractError is raised and must bubble up to the orchestrator —
agents are forbidden from suppressing it or continuing with partial state.
"""

from __future__ import annotations

import json
from typing import Optional, TypeVar

from pydantic import BaseModel, ValidationError

from .llm_provider import LLMProvider, ProviderError

T = TypeVar("T", bound=BaseModel)


class SchemaContractError(Exception):
    """Raised when an LLM output cannot be parsed/validated after one repair."""


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop the opening fence (possibly ```json) and any closing fence.
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _extract_object(text: str) -> dict:
    """Safely extract the first balanced JSON object substring, or raise."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise SchemaContractError("No JSON object found in model output.")
    candidate = text[start : end + 1]
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise SchemaContractError(f"Could not parse JSON object: {exc}") from exc
    if not isinstance(obj, dict):
        raise SchemaContractError("Extracted JSON is not an object.")
    return obj


def parse_json_object(raw_text: str) -> dict:
    """Parse raw model text into a JSON object (dict), or raise.

    Markdown-only output is accepted only if a clean JSON object can be safely
    extracted from it.
    """
    text = _strip_code_fences(raw_text)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return _extract_object(text)
    if not isinstance(obj, dict):
        raise SchemaContractError("Expected a JSON object at the top level.")
    return obj


def validate_model_object(data: dict, schema_type: type[T]) -> T:
    """Validate a dict against a Pydantic schema (raises ValidationError)."""
    return schema_type.model_validate(data)


def repair_json_once(
    provider: LLMProvider,
    model: str,
    raw_text: str,
    validation_error: Exception,
    target_schema_name: str,
) -> str:
    """Make exactly one repair attempt. Returns repaired raw text or raises."""
    system_prompt = (
        "[NOXUS_REPAIR] You are a strict JSON repair tool. "
        "Return ONLY a single valid JSON object for the requested schema. "
        "No prose, no explanation, no markdown fences."
    )
    user_prompt = (
        f"The previous output was invalid for schema '{target_schema_name}'.\n"
        f"Validation error: {validation_error}\n\n"
        f"Previous output:\n{raw_text}\n\n"
        f"Return ONLY a valid JSON object for schema '{target_schema_name}'."
    )
    try:
        return provider.complete(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema_instruction=(
                f"Output must be a JSON object valid for schema {target_schema_name}."
            ),
        )
    except ProviderError as exc:
        raise SchemaContractError(
            f"Repair attempt for '{target_schema_name}' failed at provider: {exc}"
        ) from exc


def load_validated_object(
    provider: LLMProvider,
    model: str,
    raw_text: str,
    schema_type: type[T],
    schema_name: str,
    extra_check=None,
) -> T:
    """Parse + validate with at most ONE repair attempt.

    ``extra_check`` is an optional callable run on the validated object; it may
    raise SchemaContractError/ValueError to reject an otherwise schema-valid
    object (used to enforce semantic contracts like "must contain an indirect
    prompt injection probe").
    """
    try:
        data = parse_json_object(raw_text)
        obj = validate_model_object(data, schema_type)
        if extra_check is not None:
            extra_check(obj)
        return obj
    except (SchemaContractError, ValidationError, ValueError) as first_error:
        repaired = repair_json_once(
            provider, model, raw_text, first_error, schema_name
        )
        try:
            data = parse_json_object(repaired)
            obj = validate_model_object(data, schema_type)
            if extra_check is not None:
                extra_check(obj)
            return obj
        except (SchemaContractError, ValidationError, ValueError) as second_error:
            raise SchemaContractError(
                f"Schema contract failed for '{schema_name}' after one repair "
                f"attempt: {second_error}"
            ) from second_error

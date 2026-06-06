"""Strict JSON schema contracts with a single bounded repair attempt.

The flow is: extract a JSON value from (possibly messy) model text -> optionally
normalize via a narrow, schema-specific transform -> validate against a Pydantic
schema. On any failure, exactly ONE repair attempt is made via the provider. If
that still fails, a SchemaContractError is raised and must bubble up to the
orchestrator — agents are forbidden from suppressing it or continuing with
partial state.

The extractor is hardened against common real-model output drift (markdown
fences, prose around JSON, provider response envelopes, smart quotes) but is
otherwise strict: it never uses eval, never accepts YAML as JSON, and never
fabricates missing semantic content.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import SchemaContractError
from .llm_provider import LLMProvider, ProviderError, ProviderTimeoutError

# ``SchemaContractError`` now lives in ``noxus.errors`` (so the deterministic
# patch engine need not import this JSON/agent parsing layer). It is imported
# here because json_contracts genuinely raises it; that import also keeps
# ``noxus.json_contracts.SchemaContractError`` resolving for existing callers.

T = TypeVar("T", bound=BaseModel)

# Max length of a sanitized raw-output excerpt surfaced for diagnostics.
MAX_EXCERPT_CHARS = 500


# --------------------------------------------------------------------------- #
# Sanitization
# --------------------------------------------------------------------------- #
_SECRET_SUBS = [
    (re.compile(r"(?i)(authorization\s*[:=]\s*)bearer\s+\S+"), r"\1Bearer ***REDACTED***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer ***REDACTED***"),
    (re.compile(r"(?i)(\"?api[_-]?key\"?\s*[:=]\s*\"?)[^\s\",}]+"), r"\1***REDACTED***"),
    (re.compile(r"\bsk-[A-Za-z0-9._\-]{6,}\b"), "sk-***REDACTED***"),
    (re.compile(r"\bAIza[A-Za-z0-9._\-]{10,}\b"), "***REDACTED***"),
]


def sanitize_excerpt(text: Any, max_len: int = MAX_EXCERPT_CHARS) -> str:
    """Return a short, secret-redacted snippet safe for logs and API responses."""
    if not text:
        return ""
    s = str(text)
    for pattern, repl in _SECRET_SUBS:
        s = pattern.sub(repl, s)
    s = s.strip()
    if len(s) > max_len:
        s = s[:max_len].rstrip() + "…"
    return s


# --------------------------------------------------------------------------- #
# Lenient extraction (strict about correctness, tolerant of formatting drift)
# --------------------------------------------------------------------------- #
def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


_SMART_QUOTES = {
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
}


def _normalize_smart_quotes(text: str) -> str:
    return "".join(_SMART_QUOTES.get(ch, ch) for ch in text)


def _extract_first_balanced(text: str) -> Optional[str]:
    """Return the first balanced {..} or [..] substring, respecting strings.

    Scans character-by-character tracking string state and escape sequences so
    that braces inside string literals do not confuse the balance counter.
    """
    open_to_close = {"{": "}", "[": "]"}
    for i, ch in enumerate(text):
        if ch not in open_to_close:
            continue
        depth = 0
        in_string = False
        escape = False
        for j in range(i, len(text)):
            c = text[j]
            if in_string:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    in_string = False
                continue
            if c == '"':
                in_string = True
            elif c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0:
                    return text[i : j + 1]
        # Unbalanced from this opener; try the next opener.
    return None


def _candidate_texts(raw_text: str):
    text = raw_text or ""
    yield text.strip()
    fenced = _strip_code_fences(text)
    if fenced != text.strip():
        yield fenced
    sq = _normalize_smart_quotes(fenced)
    if sq != fenced:
        yield sq


def _load_json_value(raw_text: str) -> Any:
    """Parse a JSON value (dict or list) from messy text, or raise.

    Tries: direct parse of fence/quote-normalized variants, then extraction of
    the first balanced JSON object/array. Never evaluates code.
    """
    seen = set()
    for candidate in _candidate_texts(raw_text):
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            extracted = _extract_first_balanced(candidate)
            if extracted is not None:
                try:
                    return json.loads(extracted)
                except (json.JSONDecodeError, ValueError):
                    continue
    raise SchemaContractError(
        "No parseable JSON object found in model output.",
        raw_excerpt=sanitize_excerpt(raw_text),
    )


def _unwrap_provider_envelope(value: Any) -> Any:
    """Unwrap an OpenAI-/Gemini-style response envelope to its inner JSON value.

    Only triggers when the recognizable envelope keys are present and the inner
    content parses as JSON; otherwise the value is returned unchanged.
    """
    if not isinstance(value, dict):
        return value
    inner_text: Optional[str] = None
    # OpenAI-compatible: {"choices":[{"message":{"content": "..."}}]}
    try:
        choice = value["choices"][0]
        content = choice.get("message", {}).get("content")
        if content is None:
            content = choice.get("text")
        if isinstance(content, str):
            inner_text = content
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    # Gemini-like: {"candidates":[{"content":{"parts":[{"text":"..."}]}}]}
    if inner_text is None:
        try:
            parts = value["candidates"][0]["content"]["parts"]
            inner_text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError, AttributeError):
            pass
    if inner_text:
        try:
            return _unwrap_provider_envelope(_load_json_value(inner_text))
        except SchemaContractError:
            return value
    return value


def parse_json_object(raw_text: str) -> dict:
    """Parse raw model text into a JSON object (dict), or raise.

    Handles fenced JSON, prose-wrapped JSON, provider envelopes, and smart
    quotes. A top-level array is NOT accepted here (schema-specific normalizers
    handle that case explicitly).
    """
    value = _unwrap_provider_envelope(_load_json_value(raw_text))
    if not isinstance(value, dict):
        raise SchemaContractError(
            "Expected a JSON object at the top level.",
            raw_excerpt=sanitize_excerpt(raw_text),
        )
    return value


def _coerce_to_object(
    raw_text: str, normalize: Optional[Callable[[Any], Any]]
) -> dict:
    value = _unwrap_provider_envelope(_load_json_value(raw_text))
    if normalize is not None:
        value = normalize(value)
    if not isinstance(value, dict):
        raise SchemaContractError(
            "Expected a JSON object at the top level after normalization.",
            raw_excerpt=sanitize_excerpt(raw_text),
        )
    return value


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
    except ProviderTimeoutError:
        # A timed-out (or role-attributed timeout) repair is a TRANSIENT provider
        # failure, not a schema-contract failure — let it propagate so the
        # orchestrator routes it through the timeout path (with role diagnostics)
        # instead of mislabeling it as a schema validation error.
        raise
    except ProviderError as exc:
        raise SchemaContractError(
            f"Repair attempt for '{target_schema_name}' failed at provider: {exc}",
            raw_excerpt=sanitize_excerpt(raw_text),
        ) from exc


def load_validated_object(
    provider: LLMProvider,
    model: str,
    raw_text: str,
    schema_type: type[T],
    schema_name: str,
    extra_check: Optional[Callable[[T], None]] = None,
    normalize: Optional[Callable[[Any], Any]] = None,
) -> T:
    """Parse + (optionally normalize) + validate with at most ONE repair attempt.

    ``normalize`` is a narrow, schema-specific transform applied to the parsed
    JSON value BEFORE Pydantic validation (e.g. wrap a top-level probe array, or
    rename a ``patch_operations`` alias). It must never invent semantic content.
    ``extra_check`` runs on the validated object and may reject it.
    """
    try:
        data = _coerce_to_object(raw_text, normalize)
        obj = validate_model_object(data, schema_type)
        if extra_check is not None:
            extra_check(obj)
        return obj
    except (SchemaContractError, ValidationError, ValueError) as first_error:
        repaired = repair_json_once(
            provider, model, raw_text, first_error, schema_name
        )
        try:
            data = _coerce_to_object(repaired, normalize)
            obj = validate_model_object(data, schema_type)
            if extra_check is not None:
                extra_check(obj)
            return obj
        except (SchemaContractError, ValidationError, ValueError) as second_error:
            excerpt = getattr(second_error, "raw_excerpt", None) or sanitize_excerpt(
                repaired or raw_text
            )
            raise SchemaContractError(
                f"Schema contract failed for '{schema_name}' after one repair "
                f"attempt: {second_error}",
                raw_excerpt=excerpt,
            ) from second_error

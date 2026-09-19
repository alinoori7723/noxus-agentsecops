from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import SchemaContractError
from .llm_provider import LLMProvider, ProviderError, ProviderTimeoutError

T = TypeVar("T", bound=BaseModel)


MAX_EXCERPT_CHARS = 500


_SECRET_SUBS = [
    (re.compile(r"(?i)(authorization\s*[:=]\s*)bearer\s+\S+"), r"\1Bearer ***REDACTED***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer ***REDACTED***"),
    (re.compile(r"(?i)(\"?api[_-]?key\"?\s*[:=]\s*\"?)[^\s\",}]+"), r"\1***REDACTED***"),
    (re.compile(r"\bsk-[A-Za-z0-9._\-]{6,}\b"), "sk-***REDACTED***"),
    (re.compile(r"\bAIza[A-Za-z0-9._\-]{10,}\b"), "***REDACTED***"),
]


def sanitize_excerpt(text: Any, max_len: int = MAX_EXCERPT_CHARS) -> str:

    if not text:
        return ""
    s = str(text)
    for pattern, repl in _SECRET_SUBS:
        s = pattern.sub(repl, s)
    s = s.strip()
    if len(s) > max_len:
        s = s[:max_len].rstrip() + "…"
    return s


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
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
}


def _normalize_smart_quotes(text: str) -> str:
    return "".join(_SMART_QUOTES.get(ch, ch) for ch in text)


def _extract_first_balanced(text: str) -> str | None:

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

    if not isinstance(value, dict):
        return value
    inner_text: str | None = None

    try:
        choice = value["choices"][0]
        content = choice.get("message", {}).get("content")
        if content is None:
            content = choice.get("text")
        if isinstance(content, str):
            inner_text = content
    except (KeyError, IndexError, TypeError, AttributeError):
        pass

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

    value = _unwrap_provider_envelope(_load_json_value(raw_text))
    if not isinstance(value, dict):
        raise SchemaContractError(
            "Expected a JSON object at the top level.",
            raw_excerpt=sanitize_excerpt(raw_text),
        )
    return value


def _coerce_to_object(raw_text: str, normalize: Callable[[Any], Any] | None) -> dict:
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

    return schema_type.model_validate(data)


def repair_json_once(
    provider: LLMProvider,
    model: str,
    raw_text: str,
    validation_error: Exception,
    target_schema_name: str,
) -> str:

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
    extra_check: Callable[[T], None] | None = None,
    normalize: Callable[[Any], Any] | None = None,
) -> T:

    try:
        data = _coerce_to_object(raw_text, normalize)
        obj = validate_model_object(data, schema_type)
        if extra_check is not None:
            extra_check(obj)
        return obj
    except (SchemaContractError, ValidationError, ValueError) as first_error:
        repaired = repair_json_once(provider, model, raw_text, first_error, schema_name)
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

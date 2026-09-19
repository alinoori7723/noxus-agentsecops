from __future__ import annotations

import copy
import re
from typing import Any

from .constants import SAFETY_RAIL_HEADING
from .errors import SchemaContractError
from .policy_loader import validate_policy
from .schemas import PatchOp, PatchSet

_SAFE_SEGMENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _assert_safe_policy_path(path: str) -> None:

    if (
        not isinstance(path, str)
        or not path
        or ".." in path
        or path.startswith("/")
        or "\\" in path
        or "\x00" in path
        or ":" in path
        or not all(_SAFE_SEGMENT_RE.match(seg) for seg in path.split("."))
    ):
        raise SchemaContractError(f"Patch engine refused an unsafe policy path: {path!r}.")


def _apply_safety_rail(system_prompt: str, clause_id: str, content: str, heading: str) -> str:

    clause_line = f"- ({clause_id}) {content}"
    clause_prefix = f"- ({clause_id})"

    if heading in system_prompt:
        lines = system_prompt.split("\n")
        out: list[str] = []
        replaced = False
        for line in lines:
            if line.startswith(clause_prefix):
                out.append(clause_line)
                replaced = True
            else:
                out.append(line)
        if not replaced:
            out2: list[str] = []
            for line in out:
                out2.append(line)
                if line.strip() == heading:
                    out2.append(clause_line)
            out = out2
        return "\n".join(out)

    section = f"{heading}\n{clause_line}\n\n"
    return section + system_prompt


def _set_by_path(policy: dict[str, Any], path: str, value: Any) -> None:

    _assert_safe_policy_path(path)
    keys = path.split(".")
    node = policy
    for key in keys[:-1]:
        if key not in node or not isinstance(node[key], dict):
            node[key] = {}
        node = node[key]
    node[keys[-1]] = value


def _ensure_list_member(policy: dict[str, Any], path: str, member: str) -> None:

    _assert_safe_policy_path(path)
    keys = path.split(".")
    node = policy
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    last = keys[-1]
    current = node.setdefault(last, [])
    if not isinstance(current, list):
        raise ValueError(f"Expected list at policy path '{path}'.")
    if member not in current:
        current.append(member)


def apply_patch_set(
    system_prompt: str, policy: dict[str, Any], patch_set: PatchSet
) -> tuple[str, dict[str, Any]]:

    new_prompt = system_prompt
    new_policy = copy.deepcopy(policy)

    for op in patch_set.operations:
        if op.operation is PatchOp.insert_or_update_critical_safety_rail:
            heading = op.heading or SAFETY_RAIL_HEADING
            clause_id = op.clause_id or "default_clause"
            content = op.content or ""
            new_prompt = _apply_safety_rail(new_prompt, clause_id, content, heading)

        elif op.operation is PatchOp.set_control_level:
            if op.path is not None:
                _set_by_path(new_policy, op.path, op.value)

        elif op.operation is PatchOp.add_mask_type:
            if op.mask_type is not None:
                _ensure_list_member(new_policy, "sensitive_data.mask", op.mask_type)

        elif op.operation is PatchOp.add_block_type:
            if op.block_type is not None:
                _ensure_list_member(new_policy, "sensitive_data.block", op.block_type)

        elif op.operation is PatchOp.require_human_review_for_category:
            if op.category is not None:
                _ensure_list_member(new_policy, "human_review.required_categories", op.category)

        elif op.operation is PatchOp.add_control:
            if op.path is not None:
                _set_by_path(new_policy, op.path, op.value)

        elif op.operation is PatchOp.add_output_constraint:
            if op.path is not None:
                _set_by_path(new_policy, op.path, op.value)

    try:
        validated = validate_policy(new_policy)
    except Exception as exc:
        raise SchemaContractError(f"Patched policy failed schema validation: {exc}") from exc
    return new_prompt, validated.model_dump()

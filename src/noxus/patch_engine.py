"""Deterministic patch application for system prompts and security policies.

This engine never rewrites or deletes the full system prompt, never does a full
YAML rewrite, and never reorders unrelated business instructions. It only makes
the minimal, targeted edits described by a PatchSet.
"""

from __future__ import annotations

import copy
from typing import Any

from .constants import SAFETY_RAIL_HEADING
from .policy_loader import validate_policy
from .schemas import PatchOp, PatchSet


def _apply_safety_rail(
    system_prompt: str, clause_id: str, content: str, heading: str
) -> str:
    """Insert or update the critical-safety-rail section near the top.

    Idempotent: re-applying the same clause_id never duplicates the heading or
    the clause, and the business-purpose prompt below stays intact.
    """
    clause_line = f"- ({clause_id}) {content}"
    clause_prefix = f"- ({clause_id})"

    if heading in system_prompt:
        lines = system_prompt.split("\n")
        out: list[str] = []
        replaced = False
        for line in lines:
            if line.startswith(clause_prefix):
                # Update existing clause in place (deterministic, no duplication).
                out.append(clause_line)
                replaced = True
            else:
                out.append(line)
        if not replaced:
            # Heading present but this clause is new: insert right after heading.
            out2: list[str] = []
            for line in out:
                out2.append(line)
                if line.strip() == heading:
                    out2.append(clause_line)
            out = out2
        return "\n".join(out)

    # No section yet: prepend a new one before the business-purpose prompt.
    section = f"{heading}\n{clause_line}\n\n"
    return section + system_prompt


def _set_by_path(policy: dict[str, Any], path: str, value: Any) -> None:
    """Set a dotted path in the policy dict, only on existing structure."""
    keys = path.split(".")
    node = policy
    for key in keys[:-1]:
        if key not in node or not isinstance(node[key], dict):
            node[key] = {}
        node = node[key]
    node[keys[-1]] = value


def _ensure_list_member(policy: dict[str, Any], path: str, member: str) -> None:
    """Append member to a list at the dotted path if not already present."""
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
    """Apply a PatchSet deterministically.

    Returns the patched (system_prompt, policy_dict). The patched policy is
    schema-validated before being returned.
    """
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
                _ensure_list_member(
                    new_policy, "human_review.required_categories", op.category
                )

        elif op.operation is PatchOp.add_control:
            if op.path is not None:
                _set_by_path(new_policy, op.path, op.value)

        elif op.operation is PatchOp.add_output_constraint:
            if op.path is not None:
                _set_by_path(new_policy, op.path, op.value)
        # No silent failure: any unknown operation would raise on enum creation.

    # Schema-validate the patched policy and normalize back to a plain dict.
    validated = validate_policy(new_policy)
    return new_prompt, validated.model_dump()

"""Deterministic mapping from findings to structured patch operations.

In Milestone 1 there is no LLM proposing fixes. Instead, specific finding types
map to specific, fixed PatchOperation objects. The mapper inspects the actual
findings — it never returns a hardcoded patch set blind to evaluation state.
"""

from __future__ import annotations

from .constants import (
    INDIRECT_INJECTION_CLAUSE_ID,
    INDIRECT_INJECTION_SAFETY_RAIL_TEXT,
    SAFETY_RAIL_HEADING,
)
from .schemas import Finding, PatchOp, PatchOperation, PatchSet


def _dedupe(operations: list[PatchOperation]) -> list[PatchOperation]:
    """Drop exact-duplicate operations while preserving order."""
    seen: set[tuple] = set()
    unique: list[PatchOperation] = []
    for op in operations:
        key = (
            op.operation,
            op.target,
            op.clause_id,
            op.path,
            repr(op.value),
            op.mask_type,
            op.block_type,
            op.control,
            op.constraint,
            op.category,
        )
        if key not in seen:
            seen.add(key)
            unique.append(op)
    return unique


def generate_patches_from_findings(findings: list[Finding]) -> PatchSet:
    """Inspect findings and emit the deterministic PatchSet they justify."""
    operations: list[PatchOperation] = []

    for finding in findings:
        ft = finding.finding_type

        if ft == "indirect_prompt_injection_simulated":
            operations.append(
                PatchOperation(
                    operation=PatchOp.insert_or_update_critical_safety_rail,
                    target="system_prompt",
                    clause_id=INDIRECT_INJECTION_CLAUSE_ID,
                    heading=SAFETY_RAIL_HEADING,
                    content=INDIRECT_INJECTION_SAFETY_RAIL_TEXT,
                    source_finding=ft,
                )
            )
            operations.append(
                PatchOperation(
                    operation=PatchOp.set_control_level,
                    target="policy",
                    path="prompt_injection.detect_indirect_instructions",
                    value=True,
                    source_finding=ft,
                )
            )
            operations.append(
                PatchOperation(
                    operation=PatchOp.require_human_review_for_category,
                    target="policy",
                    category="indirect_prompt_injection",
                    source_finding=ft,
                )
            )

        elif ft == "customer_identifier_leakage":
            operations.append(
                PatchOperation(
                    operation=PatchOp.add_mask_type,
                    target="policy",
                    mask_type="customer_id",
                    source_finding=ft,
                )
            )
            operations.append(
                PatchOperation(
                    operation=PatchOp.add_mask_type,
                    target="policy",
                    mask_type="internal_ticket_id",
                    source_finding=ft,
                )
            )

        elif ft == "fake_secret_exfiltration":
            operations.append(
                PatchOperation(
                    operation=PatchOp.add_block_type,
                    target="policy",
                    block_type="api_key",
                    source_finding=ft,
                )
            )
            operations.append(
                PatchOperation(
                    operation=PatchOp.require_human_review_for_category,
                    target="policy",
                    category="fake_secret_exfiltration",
                    source_finding=ft,
                )
            )

        elif ft == "pii_leakage":
            operations.append(
                PatchOperation(
                    operation=PatchOp.add_mask_type,
                    target="policy",
                    mask_type="email",
                    source_finding=ft,
                )
            )
            operations.append(
                PatchOperation(
                    operation=PatchOp.add_mask_type,
                    target="policy",
                    mask_type="phone",
                    source_finding=ft,
                )
            )

        # Any other finding type (e.g. must_not_appear_violation) intentionally
        # produces no automatic patch in Milestone 1 and remains an open risk.

    patch_set = PatchSet(operations=_dedupe(operations))
    # Schema-validate before returning / applying.
    return PatchSet.model_validate(patch_set.model_dump())

"""Deterministic remediation helpers: evidence lineage, human-review derivation,
and remediation-effectiveness telemetry.

These are PURE functions over report objects (Finding / PatchOperation /
ProbeResult). There is no LLM, no network, and no change to scoring/readiness
semantics here — they only DERIVE audit-grade metadata deterministically:

* ``derive_human_review_categories`` — final human-review categories from the
  remaining (retest) findings, so the category list can never silently disagree
  with the evidence;
* ``attach_patch_lineage`` — bind every patch operation to the finding(s) it
  addresses (source finding ids / probe ids / finding types); operations with no
  safe lineage are returned UNLINKED and must not be applied;
* ``remediation_summary`` — resolved/unresolved probe & finding counts so the UI
  can distinguish "patch applied" from "risk fixed".
"""

from __future__ import annotations

from typing import Optional

from .schemas import (
    Finding,
    PatchOp,
    PatchOperation,
    ProbeResult,
    ProbeType,
    Severity,
)

_HIGH_SEVERITY = {Severity.high, Severity.critical}

# Probe-type -> deterministic human-review category (used as a fallback when the
# finding_type is not one of the well-known deterministic markers, e.g. semantic
# judge findings).
_PROBE_CATEGORY = {
    ProbeType.indirect_prompt_injection: "prompt_injection",
    ProbeType.pii_leakage: "pii",
    ProbeType.fake_secret_exfiltration: "secrets",
    ProbeType.customer_identifier_leakage: "customer_identifier",
    ProbeType.proprietary_context_exposure: "proprietary_context",
}


# --------------------------------------------------------------------------- #
# Human-review category derivation (deterministic, from remaining findings)
# --------------------------------------------------------------------------- #
def finding_category(finding: Finding) -> Optional[str]:
    """Map a single finding to its deterministic human-review category, or None.

    finding_type is the most specific signal; probe_type is the fallback (for
    cross-probe / semantic findings). An unmapped HIGH/critical finding maps to
    ``security_review``; an unmapped low/medium finding maps to None (we never
    invent a low-risk category that is not anchored to a remaining finding).
    """
    ft = finding.finding_type
    if "indirect_prompt_injection" in ft:
        return "prompt_injection"
    if ft == "pii_leakage":
        return "pii"
    if ft == "fake_secret_exfiltration":
        return "secrets"
    if ft == "customer_identifier_leakage":
        return "customer_identifier"
    if ft == "must_not_appear_violation":
        if finding.probe_type is ProbeType.proprietary_context_exposure:
            return "proprietary_context"
        return "security_review"
    mapped = _PROBE_CATEGORY.get(finding.probe_type)
    if mapped:
        return mapped
    if finding.severity in _HIGH_SEVERITY:
        return "security_review"
    return None


def derive_human_review_categories(results: list[ProbeResult]) -> list[str]:
    """Return the sorted, deterministic human-review categories for ``results``.

    Empty when there are no findings — we never fabricate a category when no
    finding remains.
    """
    categories = set()
    for result in results:
        for finding in result.findings:
            category = finding_category(finding)
            if category:
                categories.add(category)
    return sorted(categories)


def finalize_human_review_categories(
    proposed: list[str], remaining_results: list[ProbeResult]
) -> list[str]:
    """Union LLM/policy-proposed categories with deterministic-from-findings ones.

    The deterministic categories (from the remaining/retest findings) are
    authoritative and always present; manually proposed categories are preserved
    (never silently dropped). Output is sorted and de-duplicated.
    """
    return sorted(set(proposed) | set(derive_human_review_categories(remaining_results)))


# --------------------------------------------------------------------------- #
# Patch evidence lineage
# --------------------------------------------------------------------------- #
# require_human_review_for_category category -> finding_type it addresses.
_CATEGORY_FINDING_TYPE = {
    "pii": "pii_leakage",
    "secrets": "fake_secret_exfiltration",
    "fake_secret_exfiltration": "fake_secret_exfiltration",
    "customer_identifier": "customer_identifier_leakage",
    "proprietary_context": "must_not_appear_violation",
    "indirect_prompt_injection": "indirect_prompt_injection_simulated",
    "prompt_injection": "indirect_prompt_injection_simulated",
}


def patch_target_finding_types(op: PatchOperation) -> set[str]:
    """Deterministically map a patch operation to the finding_type(s) it addresses.

    Pure structural mapping over the allowed operation/field vocabulary — it never
    invents semantics beyond the documented remediation mapping.
    """
    types: set[str] = set()
    if op.source_finding:
        types.add(op.source_finding)
    operation = op.operation

    if operation is PatchOp.set_control_level:
        if (op.path or "").endswith("detect_indirect_instructions"):
            types.add("indirect_prompt_injection_simulated")

    elif operation is PatchOp.add_mask_type:
        mask = (op.mask_type or "").lower()
        if mask in ("pii", "email", "phone"):
            types.add("pii_leakage")
        if mask in ("customer_id", "internal_ticket_id", "customer_identifier"):
            types.add("customer_identifier_leakage")

    elif operation is PatchOp.add_block_type:
        block = (op.block_type or "").lower()
        if block in ("secrets", "secret", "fake_secret", "api_key"):
            types.add("fake_secret_exfiltration")
        if block in ("proprietary_context", "proprietary", "confidential"):
            types.add("must_not_appear_violation")

    elif operation is PatchOp.require_human_review_for_category:
        mapped = _CATEGORY_FINDING_TYPE.get((op.category or "").lower())
        if mapped:
            types.add(mapped)

    elif operation is PatchOp.insert_or_update_critical_safety_rail:
        blob = " ".join(
            x for x in (op.clause_id, op.heading, op.content) if x
        ).lower()
        # Indirect-injection rails are about untrusted/embedded document
        # instructions; match those specifically (so "untrusted data" is NOT
        # misread as a PII rail, which requires explicit "pii"/"personal data").
        if any(k in blob for k in ("indirect", "injection", "untrusted", "override prior")):
            types.add("indirect_prompt_injection_simulated")
        if "pii" in blob or "data protection" in blob or "personal data" in blob:
            types.add("pii_leakage")
        if "secret" in blob or "credential" in blob:
            types.add("fake_secret_exfiltration")
        if "customer" in blob:
            types.add("customer_identifier_leakage")
        if "proprietary" in blob or "confidential" in blob:
            types.add("must_not_appear_violation")

    elif operation in (PatchOp.add_control, PatchOp.add_output_constraint):
        blob = " ".join(x for x in (op.path, op.control, op.constraint) if x).lower()
        if "indirect" in blob or "injection" in blob:
            types.add("indirect_prompt_injection_simulated")
        if "confidential" in blob or "proprietary" in blob:
            types.add("must_not_appear_violation")

    return types


def attach_patch_lineage(
    operations: list[PatchOperation], findings: list[Finding]
) -> tuple[list[PatchOperation], list[PatchOperation]]:
    """Bind each operation to the finding(s) it addresses; split linked/unlinked.

    Returns ``(linked, unlinked)``. A *linked* operation carries
    ``source_finding`` / ``source_finding_types`` / ``source_probe_ids`` /
    ``source_finding_ids`` derived from real findings in ``findings``. An
    *unlinked* operation has no safe mapping to any current finding and MUST NOT
    be applied (the caller records it as a rejected/unlinked proposal).
    """
    by_type: dict[str, list[Finding]] = {}
    by_probe: dict[str, list[Finding]] = {}
    by_id: dict[str, Finding] = {}
    for finding in findings:
        by_type.setdefault(finding.finding_type, []).append(finding)
        by_probe.setdefault(finding.probe_id, []).append(finding)
        by_id[f"{finding.probe_id}:{finding.finding_type}"] = finding

    linked: list[PatchOperation] = []
    unlinked: list[PatchOperation] = []
    for op in operations:
        target_types = patch_target_finding_types(op)
        matched = [f for t in target_types for f in by_type.get(t, [])]
        # Honor (validate) any LLM-cited finding/probe ids that actually exist in
        # the current finding set — deterministic op-type mapping above is the
        # safe fallback / relink when cited ids are missing.
        for fid in op.source_finding_ids:
            if fid in by_id:
                matched.append(by_id[fid])
        for pid in op.source_probe_ids:
            matched.extend(by_probe.get(pid, []))
        if not matched:
            unlinked.append(op)
            continue
        finding_types = sorted({f.finding_type for f in matched})
        probe_ids = sorted({f.probe_id for f in matched})
        finding_ids = sorted({f"{f.probe_id}:{f.finding_type}" for f in matched})
        linked.append(
            op.model_copy(
                update={
                    "source_finding": op.source_finding or finding_types[0],
                    "source_finding_types": finding_types,
                    "source_probe_ids": probe_ids,
                    "source_finding_ids": finding_ids,
                }
            )
        )
    return linked, unlinked


def patch_lineage_label(op: PatchOperation) -> str:
    """A short, never-empty lineage label for display (never 'not specified')."""
    if op.source_finding_ids:
        return ", ".join(op.source_finding_ids)
    if op.source_probe_ids:
        return ", ".join(op.source_probe_ids)
    if op.source_finding_types:
        return ", ".join(op.source_finding_types)
    if op.source_finding:
        return op.source_finding
    return "unlinked"


# --------------------------------------------------------------------------- #
# Remediation-effectiveness counts
# --------------------------------------------------------------------------- #
def remediation_summary(
    before_results: list[ProbeResult], after_results: list[ProbeResult]
) -> dict:
    """Resolved/unresolved probe & finding counts comparing before vs after."""
    before_by_id = {r.probe_id: r for r in before_results}
    resolved_probes = 0
    unresolved_probes = 0
    for after in after_results:
        before = before_by_id.get(after.probe_id)
        before_failed = before is not None and not before.passed
        if before_failed and after.passed:
            resolved_probes += 1
        if not after.passed:
            unresolved_probes += 1
    before_findings = sum(len(r.findings) for r in before_results)
    after_findings = sum(len(r.findings) for r in after_results)
    return {
        "resolved_probe_count": resolved_probes,
        "unresolved_probe_count": unresolved_probes,
        "resolved_finding_count": max(0, before_findings - after_findings),
        "unresolved_finding_count": after_findings,
    }

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

# Specific-domain finding types. A patch whose target/effect domain is one of
# these maps PRIMARILY to that finding type — it must never be re-attributed to
# the generic ``must_not_appear_violation`` merely because that finding
# co-occurred (or sorts first alphabetically). See ``_select_primary_finding_type``.
_SPECIFIC_DOMAIN_FINDING_TYPES = {
    "pii_leakage",
    "fake_secret_exfiltration",
    "customer_identifier_leakage",
    "indirect_prompt_injection_simulated",
}

# finding_type -> category family, used to decide whether a SECONDARY finding is
# causally related to the primary (same family) for "Related findings" display.
_FINDING_TYPE_FAMILY = {
    "indirect_prompt_injection_simulated": "prompt_injection",
    "pii_leakage": "pii",
    "fake_secret_exfiltration": "secrets",
    "customer_identifier_leakage": "customer_identifier",
    "must_not_appear_violation": "proprietary_context",
}

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


def patch_primary_finding_type(op: PatchOperation) -> Optional[str]:
    """The SINGLE finding type a patch is principally meant to remediate.

    Precise (not a keyword union): used to compute applied-patch status from the
    primary target so a prompt-injection patch isn't judged by an unrelated
    co-occurring finding. Priority is fixed and deterministic.
    """
    operation = op.operation
    if operation is PatchOp.set_control_level:
        if (op.path or "").endswith("detect_indirect_instructions"):
            return "indirect_prompt_injection_simulated"
    elif operation is PatchOp.add_mask_type:
        mask = (op.mask_type or "").lower()
        if mask in ("customer_id", "internal_ticket_id", "customer_identifier"):
            return "customer_identifier_leakage"
        if mask in ("pii", "email", "phone"):
            return "pii_leakage"
    elif operation is PatchOp.add_block_type:
        block = (op.block_type or "").lower()
        if block in ("secrets", "secret", "fake_secret", "api_key"):
            return "fake_secret_exfiltration"
        if block in ("proprietary_context", "proprietary", "confidential"):
            return "must_not_appear_violation"
    elif operation is PatchOp.require_human_review_for_category:
        return _CATEGORY_FINDING_TYPE.get((op.category or "").lower())
    elif operation is PatchOp.insert_or_update_critical_safety_rail:
        blob = " ".join(x for x in (op.clause_id, op.heading, op.content) if x).lower()
        if any(k in blob for k in ("indirect", "injection", "untrusted", "override prior")):
            return "indirect_prompt_injection_simulated"
        if "secret" in blob or "credential" in blob:
            return "fake_secret_exfiltration"
        if "customer" in blob:
            return "customer_identifier_leakage"
        if "proprietary" in blob or "confidential" in blob:
            return "must_not_appear_violation"
        if "pii" in blob or "personal data" in blob or "data protection" in blob:
            return "pii_leakage"
    elif operation in (PatchOp.add_control, PatchOp.add_output_constraint):
        blob = " ".join(x for x in (op.path, op.control, op.constraint) if x).lower()
        if "indirect" in blob or "injection" in blob:
            return "indirect_prompt_injection_simulated"
        if "confidential" in blob or "proprietary" in blob:
            return "must_not_appear_violation"
    return op.source_finding


def _select_primary_finding_type(
    intended: Optional[str], finding_types: list[str]
) -> Optional[str]:
    """Choose the PRIMARY finding type from the patch domain, not co-occurrence.

    Rules (deterministic):
    1. The patch's own intended domain wins when it is actually among the matched
       findings.
    2. Otherwise a specific-domain finding (pii/secret/customer/injection) is
       preferred over the generic ``must_not_appear_violation`` — the generic
       finding is never chosen merely because it sorts first alphabetically or
       happened to co-occur.
    3. If no specific-domain finding was matched but the patch's own domain IS
       specific, attribute to that domain (e.g. a PII patch linked only via a
       cited proprietary probe must not be labeled ``must_not_appear_violation``).
    4. Only a generic / proprietary-context control falls back to the (generic)
       matched finding as its primary.
    """
    if intended and intended in finding_types:
        return intended
    specifics = [t for t in finding_types if t in _SPECIFIC_DOMAIN_FINDING_TYPES]
    if specifics:
        return specifics[0]
    if intended in _SPECIFIC_DOMAIN_FINDING_TYPES:
        return intended
    return finding_types[0] if finding_types else intended


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
        # PRIMARY target: the precise finding type this op principally remediates,
        # constrained to a type actually present in the matched findings; else the
        # first matched type. The primary probe is a matched probe of that type.
        primary_type = _select_primary_finding_type(
            patch_primary_finding_type(op), finding_types
        )
        primary_probe = next(
            (f.probe_id for f in matched if f.finding_type == primary_type), probe_ids[0]
        )
        primary_id = f"{primary_probe}:{primary_type}"
        secondary_ids = [fid for fid in finding_ids if fid != primary_id]
        linked.append(
            op.model_copy(
                update={
                    "source_finding": op.source_finding or primary_type,
                    "source_finding_types": finding_types,
                    "source_probe_ids": probe_ids,
                    "source_finding_ids": finding_ids,
                    "primary_source_finding_type": primary_type,
                    "primary_source_probe_id": primary_probe,
                    "secondary_source_finding_ids": secondary_ids,
                }
            )
        )
    return linked, unlinked


def patch_status(op: PatchOperation, unresolved_finding_types) -> str:
    """Applied-patch status computed from the PRIMARY target, not broad links.

    * rejected_unlinked — no valid lineage at all.
    * applied_requires_human_review — human-review op, or primary is the
      unsupported proprietary-context finding (kept as an open risk).
    * applied_but_primary_unresolved — the primary finding type still fails retest.
    * applied_but_related_risk_unresolved — primary resolved, but a SECONDARY
      (related) finding type this op also touched still fails retest.
    * applied_and_resolved — primary resolved and no related risk remains.
    """
    unresolved = set(unresolved_finding_types or [])
    has_lineage = bool(
        op.primary_source_finding_type
        or op.source_finding_ids
        or op.source_probe_ids
        or op.source_finding_types
        or op.source_finding
    )
    if not has_lineage:
        return "rejected_unlinked"
    primary = (
        op.primary_source_finding_type
        or (op.source_finding_types[0] if op.source_finding_types else op.source_finding)
    )
    if op.operation is PatchOp.require_human_review_for_category:
        return "applied_requires_human_review"
    if primary == "must_not_appear_violation":
        # Proprietary-context exposure has no approved auto-remediation.
        return "applied_requires_human_review"
    if primary in unresolved:
        return "applied_but_primary_unresolved"
    secondary = set(op.source_finding_types) - {primary}
    if secondary & unresolved:
        return "applied_but_related_risk_unresolved"
    return "applied_and_resolved"


def derive_human_review_mapping(
    final_categories: list[str], after_results: list[ProbeResult]
) -> list[dict]:
    """Per-category derivation rows tying each category to unresolved findings.

    For each final human-review category, returns its supporting unresolved
    retest finding types/probe ids. A category with no supporting unresolved
    finding is flagged ``proposed_by_agent`` (vs ``derived_from_retest``).
    """
    by_cat_types: dict[str, set] = {}
    by_cat_probes: dict[str, set] = {}
    for result in after_results:
        for finding in result.findings:
            category = finding_category(finding)
            if not category:
                continue
            by_cat_types.setdefault(category, set()).add(finding.finding_type)
            by_cat_probes.setdefault(category, set()).add(finding.probe_id)

    rows: list[dict] = []
    for category in sorted(final_categories):
        types = sorted(by_cat_types.get(category, set()))
        probes = sorted(by_cat_probes.get(category, set()))
        if types:
            reason = (
                f"Derived from {len(probes)} unresolved retest finding(s): "
                f"{', '.join(types)}."
            )
            source = "derived_from_retest"
        else:
            reason = (
                "Proposed by the tuning agent; no unresolved retest finding "
                "currently supports it."
            )
            source = "proposed_by_agent"
        rows.append(
            {
                "category": category,
                "derived_from_finding_types": types,
                "derived_from_probe_ids": probes,
                "source": source,
                "reason": reason,
            }
        )
    return rows


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


def _finding_type_family(finding_type: Optional[str]) -> Optional[str]:
    if not finding_type:
        return None
    return _FINDING_TYPE_FAMILY.get(finding_type, finding_type)


def _split_finding_id(finding_id: str) -> tuple[str, str]:
    probe, _, finding_type = finding_id.partition(":")
    return probe, finding_type


def related_secondary_finding_ids(op: PatchOperation) -> list[str]:
    """Secondary finding ids that are CAUSALLY related to the primary lineage.

    A secondary finding is "related" only when it shares the primary's causal
    probe chain (same probe id) or its category family. Unrelated cross-domain
    co-occurrences — e.g. a customer-identifier finding pulled in beside a
    prompt-injection primary via a broadly-cited probe — are NOT presented as a
    related/secondary source (they remain in ``secondary_source_finding_ids`` for
    the audit trail, but are not shown as direct evidence sources).
    """
    primary_probe = op.primary_source_probe_id
    primary_family = _finding_type_family(op.primary_source_finding_type)
    related: list[str] = []
    for fid in op.secondary_source_finding_ids:
        probe, finding_type = _split_finding_id(fid)
        if primary_probe and probe == primary_probe:
            related.append(fid)
        elif primary_family and _finding_type_family(finding_type) == primary_family:
            related.append(fid)
    return related


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

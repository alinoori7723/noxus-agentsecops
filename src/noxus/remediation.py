from __future__ import annotations

from .schemas import (
    Finding,
    PatchOp,
    PatchOperation,
    ProbeResult,
    ProbeType,
    Severity,
)

_HIGH_SEVERITY = {Severity.high, Severity.critical}


_SEVERITY_ORDER = {
    Severity.low: 1,
    Severity.medium: 2,
    Severity.high: 3,
    Severity.critical: 4,
}


_SPECIFIC_DOMAIN_FINDING_TYPES = {
    "pii_leakage",
    "fake_secret_exfiltration",
    "customer_identifier_leakage",
    "indirect_prompt_injection_simulated",
}


_FINDING_TYPE_FAMILY = {
    "indirect_prompt_injection_simulated": "prompt_injection",
    "indirect_prompt_injection": "prompt_injection",
    "pii_leakage": "pii",
    "fake_secret_exfiltration": "secrets",
    "customer_identifier_leakage": "customer_identifier",
    "proprietary_context_exposure": "proprietary_context",
    "must_not_appear_violation": "proprietary_context",
}


_PATCH_DOMAIN_KEYWORDS = (
    (
        "prompt_injection",
        (
            "prompt_injection",
            "indirect_injection",
            "indirect",
            "injection",
            "untrusted",
            "override prior",
        ),
    ),
    ("pii", ("pii", "personal data", "personal_data", "email", "phone")),
    ("secrets", ("secret", "api_key", "api key", "token", "credential")),
    (
        "customer_identifier",
        (
            "customer_identifier",
            "customer_id",
            "ticket_id",
            "internal_ticket",
            "account_id",
            "customer",
        ),
    ),
    (
        "proprietary_context",
        ("proprietary", "confidential", "internal_context", "business_context"),
    ),
)


_SPECIFIC_PATCH_DOMAINS = {"prompt_injection", "pii", "secrets", "customer_identifier"}


_DOMAIN_PRIMARY_PRECEDENCE = {
    "prompt_injection": ["indirect_prompt_injection_simulated", "indirect_prompt_injection"],
    "pii": ["pii_leakage"],
    "secrets": ["fake_secret_exfiltration"],
    "customer_identifier": ["customer_identifier_leakage"],
    "proprietary_context": ["proprietary_context_exposure", "must_not_appear_violation"],
    "generic_policy": ["must_not_appear_violation"],
}


def patch_domain(op: PatchOperation) -> str:

    operation = getattr(op.operation, "value", op.operation)
    blob = " ".join(
        str(x)
        for x in (
            op.target,
            op.path,
            operation,
            op.mask_type,
            op.block_type,
            op.category,
            op.control,
            op.constraint,
            op.clause_id,
            op.heading,
            op.content,
            op.value,
            op.source_finding,
        )
        if x is not None
    ).lower()
    for domain, keywords in _PATCH_DOMAIN_KEYWORDS:
        if any(k in blob for k in keywords):
            return domain
    return "generic_policy"


_PROBE_CATEGORY = {
    ProbeType.indirect_prompt_injection: "prompt_injection",
    ProbeType.pii_leakage: "pii",
    ProbeType.fake_secret_exfiltration: "secrets",
    ProbeType.customer_identifier_leakage: "customer_identifier",
    ProbeType.proprietary_context_exposure: "proprietary_context",
}


def finding_category(finding: Finding) -> str | None:

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

    return sorted(set(proposed) | set(derive_human_review_categories(remaining_results)))


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
        blob = " ".join(x for x in (op.clause_id, op.heading, op.content) if x).lower()

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


def patch_primary_finding_type(op: PatchOperation) -> str | None:

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


def _select_primary_finding_type(op: PatchOperation, finding_types: list[str]) -> str | None:

    domain = patch_domain(op)
    for preferred in _DOMAIN_PRIMARY_PRECEDENCE.get(domain, []):
        if preferred in finding_types:
            return preferred
    specifics = sorted(t for t in finding_types if t in _SPECIFIC_DOMAIN_FINDING_TYPES)
    if specifics:
        return specifics[0]
    if domain in _SPECIFIC_PATCH_DOMAINS:
        return _DOMAIN_PRIMARY_PRECEDENCE[domain][0]
    return finding_types[0] if finding_types else op.source_finding


def attach_patch_lineage(
    operations: list[PatchOperation], findings: list[Finding]
) -> tuple[list[PatchOperation], list[PatchOperation]]:

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

        primary_type = _select_primary_finding_type(op, finding_types)

        cited_probes = set(op.source_probe_ids)
        candidates = [f for f in matched if f.finding_type == primary_type]
        if candidates:
            primary_probe = min(
                candidates,
                key=lambda f: (
                    0 if f.probe_id in cited_probes else 1,
                    -_SEVERITY_ORDER.get(f.severity, 0),
                    f.probe_id,
                ),
            ).probe_id
        else:
            primary_probe = probe_ids[0]
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
    primary = op.primary_source_finding_type or (
        op.source_finding_types[0] if op.source_finding_types else op.source_finding
    )
    if op.operation is PatchOp.require_human_review_for_category:
        return "applied_requires_human_review"
    if primary == "must_not_appear_violation":
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
            reason = f"Derived from {len(probes)} unresolved retest finding(s): {', '.join(types)}."
            source = "derived_from_retest"
        else:
            reason = (
                "Proposed by the tuning agent; no unresolved retest finding currently supports it."
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

    if op.source_finding_ids:
        return ", ".join(op.source_finding_ids)
    if op.source_probe_ids:
        return ", ".join(op.source_probe_ids)
    if op.source_finding_types:
        return ", ".join(op.source_finding_types)
    if op.source_finding:
        return op.source_finding
    return "unlinked"


def _finding_type_family(finding_type: str | None) -> str | None:
    if not finding_type:
        return None
    return _FINDING_TYPE_FAMILY.get(finding_type, finding_type)


def _split_finding_id(finding_id: str) -> tuple[str, str]:
    probe, _, finding_type = finding_id.partition(":")
    return probe, finding_type


def related_secondary_finding_ids(op: PatchOperation) -> list[str]:

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


def classify_related_findings(op: PatchOperation) -> dict:

    primary_probe = op.primary_source_probe_id
    primary_family = _finding_type_family(op.primary_source_finding_type)
    domain = patch_domain(op)
    same_category: list[str] = []
    same_probe: list[str] = []
    generic: list[str] = []
    for fid in op.secondary_source_finding_ids:
        probe, finding_type = _split_finding_id(fid)
        family = _finding_type_family(finding_type)
        if primary_family and family == primary_family:
            same_category.append(fid)
        elif primary_probe and probe == primary_probe:
            same_probe.append(fid)
        elif domain in ("generic_policy", "proprietary_context"):
            generic.append(fid)

    return {
        "same_category_related": same_category,
        "leakage_from_same_probe": same_probe,
        "generic_policy_related": generic,
    }


def unresolved_finding_instances(after_results: list[ProbeResult]) -> list[dict]:

    instances: list[dict] = []
    index = 0
    for result in after_results:
        for finding in result.findings:
            instances.append(
                {
                    "instance_id": f"{finding.probe_id}:{finding.finding_type}#{index}",
                    "finding_type": finding.finding_type,
                    "probe_id": finding.probe_id,
                    "severity": _value_severity(finding.severity),
                    "category": finding_category(finding),
                }
            )
            index += 1
    return instances


def _value_severity(severity) -> str:
    return getattr(severity, "value", None) or str(severity)


def route_unresolved_instances(
    after_results: list[ProbeResult], final_categories: list[str]
) -> dict:

    instances = unresolved_finding_instances(after_results)
    final = set(final_categories)
    by_cat: dict[str, dict] = {}
    not_reviewed: list[dict] = []
    for inst in instances:
        category = inst["category"]
        if category and category in final:
            row = by_cat.setdefault(
                category,
                {"instance_ids": [], "types": set(), "probes": set()},
            )
            row["instance_ids"].append(inst["instance_id"])
            row["types"].add(inst["finding_type"])
            row["probes"].add(inst["probe_id"])
        else:
            reason = (
                "No human-review category maps to this finding type."
                if not category
                else (f"Category {category!r} is not in the final human-review list.")
            )
            not_reviewed.append({**inst, "reason": reason})

    derivation: list[dict] = []
    for category in sorted(final):
        category_row = by_cat.get(category)
        if category_row:
            row = category_row
            types = sorted(row["types"])
            probes = sorted(row["probes"])
            derivation.append(
                {
                    "category": category,
                    "derived_from_finding_instance_ids": sorted(row["instance_ids"]),
                    "derived_from_finding_types": types,
                    "derived_from_probe_ids": probes,
                    "source": "derived_from_retest",
                    "reason": (
                        f"Derived from {len(row['instance_ids'])} unresolved retest "
                        f"finding instance(s) across {len(probes)} probe(s): "
                        f"{', '.join(types)}."
                    ),
                }
            )
        else:
            derivation.append(
                {
                    "category": category,
                    "derived_from_finding_instance_ids": [],
                    "derived_from_finding_types": [],
                    "derived_from_probe_ids": [],
                    "source": "proposed_by_agent",
                    "reason": (
                        "Proposed by the tuning agent; no unresolved retest finding "
                        "currently supports it."
                    ),
                }
            )

    routed_instance_ids = [
        fid for row in derivation for fid in row["derived_from_finding_instance_ids"]
    ]
    routed_types = sorted({t for row in derivation for t in row["derived_from_finding_types"]})
    return {
        "unresolved_finding_instances": instances,
        "unresolved_finding_types": sorted({i["finding_type"] for i in instances}),
        "human_review_derivation": derivation,
        "unresolved_not_human_reviewed": not_reviewed,
        "human_review_derived_finding_instance_count": len(routed_instance_ids),
        "human_review_derived_finding_type_count": len(routed_types),
    }


def remediation_summary(
    before_results: list[ProbeResult], after_results: list[ProbeResult]
) -> dict:

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

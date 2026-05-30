from noxus.constants import (
    INDIRECT_INJECTION_CLAUSE_ID,
    INDIRECT_INJECTION_SAFETY_RAIL_TEXT,
    SAFETY_RAIL_HEADING,
)
from noxus.patch_engine import apply_patch_set
from noxus.policy_loader import validate_policy
from noxus.schemas import PatchOp, PatchOperation, PatchSet

BUSINESS_PROMPT = (
    "You are SupportBot.\n"
    "Business purpose:\n"
    "- Help customers with billing.\n"
    "- Summarize attached documents."
)

BASE_POLICY = {
    "sensitive_data": {"block": ["api_key"], "mask": []},
    "prompt_injection": {"mode": "basic", "detect_indirect_instructions": False},
    "output_policy": {
        "block_confidential": True,
        "require_evidence_for_policy_claims": False,
    },
    "human_review": {"required_categories": []},
}


def _safety_rail_patch():
    return PatchSet(
        operations=[
            PatchOperation(
                operation=PatchOp.insert_or_update_critical_safety_rail,
                target="system_prompt",
                clause_id=INDIRECT_INJECTION_CLAUSE_ID,
                heading=SAFETY_RAIL_HEADING,
                content=INDIRECT_INJECTION_SAFETY_RAIL_TEXT,
            )
        ]
    )


def test_safety_rail_inserted_near_top():
    prompt, _ = apply_patch_set(BUSINESS_PROMPT, BASE_POLICY, _safety_rail_patch())
    assert prompt.startswith(SAFETY_RAIL_HEADING)
    # Heading must come before the business purpose section.
    assert prompt.index(SAFETY_RAIL_HEADING) < prompt.index("Business purpose")


def test_safety_rail_patch_is_idempotent():
    patch = _safety_rail_patch()
    prompt1, _ = apply_patch_set(BUSINESS_PROMPT, BASE_POLICY, patch)
    prompt2, _ = apply_patch_set(prompt1, BASE_POLICY, patch)
    assert prompt1 == prompt2
    assert prompt2.count(SAFETY_RAIL_HEADING) == 1
    assert prompt2.count(f"- ({INDIRECT_INJECTION_CLAUSE_ID})") == 1


def test_business_prompt_preserved_after_patch():
    prompt, _ = apply_patch_set(BUSINESS_PROMPT, BASE_POLICY, _safety_rail_patch())
    assert BUSINESS_PROMPT in prompt
    assert "Help customers with billing." in prompt
    assert "Summarize attached documents." in prompt


def test_policy_patch_enables_indirect_instruction_detection():
    patch = PatchSet(
        operations=[
            PatchOperation(
                operation=PatchOp.set_control_level,
                target="policy",
                path="prompt_injection.detect_indirect_instructions",
                value=True,
            )
        ]
    )
    _, policy = apply_patch_set(BUSINESS_PROMPT, BASE_POLICY, patch)
    assert policy["prompt_injection"]["detect_indirect_instructions"] is True


def test_policy_patch_validates_after_application():
    patch = PatchSet(
        operations=[
            PatchOperation(
                operation=PatchOp.add_mask_type, target="policy", mask_type="customer_id"
            ),
            PatchOperation(
                operation=PatchOp.add_mask_type,
                target="policy",
                mask_type="internal_ticket_id",
            ),
            PatchOperation(
                operation=PatchOp.add_block_type, target="policy", block_type="api_key"
            ),
            PatchOperation(
                operation=PatchOp.require_human_review_for_category,
                target="policy",
                category="indirect_prompt_injection",
            ),
        ]
    )
    _, policy = apply_patch_set(BUSINESS_PROMPT, BASE_POLICY, patch)
    # Patched policy must still satisfy the strict schema.
    validated = validate_policy(policy)
    assert "customer_id" in validated.sensitive_data.mask
    assert "internal_ticket_id" in validated.sensitive_data.mask
    # api_key should not be duplicated.
    assert validated.sensitive_data.block.count("api_key") == 1
    assert "indirect_prompt_injection" in validated.human_review.required_categories

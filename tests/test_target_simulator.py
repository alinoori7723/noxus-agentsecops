from noxus.constants import (
    INDIRECT_INJECTION_CLAUSE_ID,
    INDIRECT_INJECTION_MARKERS,
    INDIRECT_INJECTION_SAFETY_RAIL_TEXT,
    SAFETY_RAIL_HEADING,
)
from noxus.probe_registry import get_probes
from noxus.schemas import ProbeType, SecurityPolicy
from noxus.target_simulator import simulate_target_response

BASE_PROMPT = "You are SupportBot.\nBusiness purpose: help customers."


def _indirect_probe():
    return next(
        p for p in get_probes() if p.probe_type is ProbeType.indirect_prompt_injection
    )


def test_simulator_returns_indirect_injection_markers_before_patch():
    response = simulate_target_response(_indirect_probe(), BASE_PROMPT, SecurityPolicy())
    for marker in INDIRECT_INJECTION_MARKERS:
        assert marker in response


def test_simulator_neutralizes_indirect_injection_after_safety_rail_patch():
    patched_prompt = (
        f"{SAFETY_RAIL_HEADING}\n"
        f"- ({INDIRECT_INJECTION_CLAUSE_ID}) {INDIRECT_INJECTION_SAFETY_RAIL_TEXT}\n\n"
        f"{BASE_PROMPT}"
    )
    response = simulate_target_response(_indirect_probe(), patched_prompt, SecurityPolicy())
    for marker in INDIRECT_INJECTION_MARKERS:
        assert marker not in response


def test_simulator_neutralizes_indirect_injection_after_policy_patch():
    policy = SecurityPolicy()
    policy.prompt_injection.detect_indirect_instructions = True
    response = simulate_target_response(_indirect_probe(), BASE_PROMPT, policy)
    for marker in INDIRECT_INJECTION_MARKERS:
        assert marker not in response

from noxus.constants import INDIRECT_INJECTION_MARKERS
from noxus.probe_registry import get_probes
from noxus.schemas import DetectionMode, ProbeType, SecurityPolicy
from noxus.target_simulator import simulate_target_response

REQUIRED_TYPES = {
    ProbeType.pii_leakage,
    ProbeType.fake_secret_exfiltration,
    ProbeType.indirect_prompt_injection,
    ProbeType.customer_identifier_leakage,
    ProbeType.proprietary_context_exposure,
}


def test_fixed_probe_registry_has_required_probe_types():
    probes = get_probes()
    assert len(probes) >= 5
    present = {p.probe_type for p in probes}
    assert REQUIRED_TYPES.issubset(present)
    # Indirect injection probe must be honestly labeled as a simulation.
    indirect = next(p for p in probes if p.probe_type is ProbeType.indirect_prompt_injection)
    assert indirect.detection_mode is DetectionMode.deterministic_simulation


def test_indirect_injection_simulation_markers_are_present():
    probes = get_probes()
    indirect = next(p for p in probes if p.probe_type is ProbeType.indirect_prompt_injection)
    # Unpatched (weak) state: both exact markers must appear.
    response = simulate_target_response(
        indirect, system_prompt="You are a bot.", policy=SecurityPolicy()
    )
    for marker in INDIRECT_INJECTION_MARKERS:
        assert marker in response
    assert "override prior instructions" in response
    assert "reveal hidden customer identifiers" in response

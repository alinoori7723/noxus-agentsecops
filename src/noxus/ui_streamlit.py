"""Minimal local Streamlit demo UI for Noxus AgentSecOps.

This is the ONLY module allowed to import Streamlit. It contains no core logic:
it loads inputs, calls the already-accepted orchestrator, and renders the
results using the pure-Python helpers in ``ui_formatters``.

Run locally with:
    streamlit run src/noxus/ui_streamlit.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml

# Absolute imports so `streamlit run src/noxus/ui_streamlit.py` works (Streamlit
# executes this file as a script, where relative imports are unavailable).
from noxus import ui_formatters
from noxus.cli import _build_provider_from_env, _models_from_env
from noxus.llm_provider import ProviderError
from noxus.orchestrator import run_readiness_assessment
from noxus.policy_loader import validate_policy

_SAMPLES = Path(__file__).resolve().parent / "samples"


def _read_sample(name: str) -> str:
    try:
        return (_SAMPLES / name).read_text(encoding="utf-8")
    except OSError:
        return ""


def _init_session_state() -> None:
    """Initialize editable inputs from sample files exactly once."""
    if "system_prompt_text" not in st.session_state:
        st.session_state.system_prompt_text = _read_sample("system_prompt.txt")
    if "security_policy_yaml_text" not in st.session_state:
        st.session_state.security_policy_yaml_text = _read_sample(
            "security_policy.yaml"
        )
    if "business_context_text" not in st.session_state:
        st.session_state.business_context_text = _read_sample("business_context.md")
    if "last_report" not in st.session_state:
        st.session_state.last_report = None


def _render_header() -> None:
    st.title("Noxus AgentSecOps")
    st.caption(
        "Autonomous red-team and policy tuning for enterprise AI apps."
    )
    st.info(
        "Pre-production readiness tester, not a runtime firewall. "
        "Local demo presentation only — no cloud, no compliance certification."
    )


def _render_badge(badge: dict) -> None:
    color_to_emoji = {"green": "🟢", "amber": "🟠", "red": "🔴"}
    emoji = color_to_emoji.get(badge["color"], "🔴")
    st.subheader(f"{emoji} Readiness: {badge['label']} ({badge['color'].upper()})")
    if badge["state"] == "CONDITIONAL_PASS":
        st.warning(
            "CONDITIONAL_PASS with open risk(s) is intentional and honest — "
            "it is not a PASS."
        )


def _render_timeline(report) -> None:
    st.header("Iteration Timeline")
    timeline = ui_formatters.build_iteration_timeline(report)
    cols = st.columns(len(timeline))
    for col, entry in zip(cols, timeline):
        with col:
            st.metric(
                label=entry["label"],
                value=f"{entry['score']}/100",
                delta=entry.get("score_delta"),
            )
            st.write(f"Failed probes: {entry['failed_probes']}/{entry['total_probes']}")
    after = timeline[-1]
    st.write(
        f"Mode: `{after.get('mode')}` · tuning iterations: "
        f"`{after.get('tuning_iterations')}` · final state: "
        f"**{after.get('readiness_state')}**"
    )


def _render_red_blue(report) -> None:
    st.header("Red / Blue Dashboard")
    model = ui_formatters.build_red_blue_dashboard_model(report)
    left, right = st.columns(2)
    with left:
        st.subheader(model["red"]["title"])
        for probe in model["red"]["probes"]:
            st.markdown(
                f"**{probe['status']}** · `{probe['probe_id']}` "
                f"({probe['probe_type']}) {probe['detection_label']}"
            )
            for snippet in probe["evidence"]:
                st.code(snippet, language="text")
    with right:
        st.subheader(model["blue"]["title"])
        st.caption(model["blue"]["patch_engine_note"])
        for patch in model["blue"]["patches"]:
            st.markdown(
                f"- `{patch['operation']}` → {patch['target']} "
                f"({patch['detail']})"
            )
        preview = model["blue"]["safety_rail_preview"]
        if "[CRITICAL_SAFETY_RAILS]" in preview:
            st.markdown("**[CRITICAL_SAFETY_RAILS] insertion preview:**")
            st.code(preview, language="text")
        else:
            st.caption(preview)


def _render_evidence(report) -> None:
    st.header("Evidence Report")
    model = ui_formatters.build_evidence_report_model(report)
    for finding in model["findings"]:
        confidence = (
            f" · confidence: {finding['confidence']}"
            if finding["confidence"]
            else ""
        )
        st.markdown(
            f"- **{finding['finding_type']}** "
            f"(severity: {finding['severity']}) "
            f"{finding['detection_label']}{confidence} "
            f"→ remediation: {finding['remediation_target']}"
        )
        st.code(finding["evidence"], language="text")

    st.subheader("Open Risks")
    if model["open_risks"]:
        for risk in model["open_risks"]:
            st.error(risk)
    else:
        st.success("No open risks.")

    if model["proprietary_context_exposure_unresolved"]:
        st.warning(
            "Proprietary-context exposure remains an UNRESOLVED open risk "
            "(no approved auto-remediation in this milestone)."
        )

    if model["human_review_requirements"]:
        st.subheader("Human Review Requirements")
        for req in model["human_review_requirements"]:
            st.write(f"- {req}")


def _run_assessment(mode: str):
    raw_policy = yaml.safe_load(st.session_state.security_policy_yaml_text) or {}
    validate_policy(raw_policy)  # surface malformed policy early

    if mode == "agent_assisted":
        try:
            provider = _build_provider_from_env()
        except ProviderError as exc:
            st.warning(
                f"Agent-assisted mode unavailable: {exc} "
                "Your edits are preserved; switch to Deterministic Mode to run."
            )
            return None
        return run_readiness_assessment(
            system_prompt=st.session_state.system_prompt_text,
            policy=raw_policy,
            business_context_text=st.session_state.business_context_text,
            mode="agent_assisted",
            provider=provider,
            **_models_from_env(),
        )

    return run_readiness_assessment(
        system_prompt=st.session_state.system_prompt_text,
        policy=raw_policy,
        business_context_text=st.session_state.business_context_text,
        mode="deterministic",
    )


def main() -> None:
    st.set_page_config(page_title="Noxus AgentSecOps", layout="wide")
    _init_session_state()
    _render_header()

    mode_label = st.radio(
        "Mode",
        ["Deterministic Mode", "Agent-Assisted Mode"],
        index=0,
    )
    mode = "agent_assisted" if mode_label.startswith("Agent") else "deterministic"
    if mode == "agent_assisted":
        st.caption(
            "Agent-assisted mode needs NOXUS_LLM_BASE_URL and NOXUS_LLM_API_KEY. "
            "Deterministic mode needs no credentials."
        )

    st.header("Target Configuration")
    # Bind each widget to a session_state key so edits survive reruns.
    st.text_area("System prompt", key="system_prompt_text", height=180)
    st.text_area("Security policy (YAML)", key="security_policy_yaml_text", height=180)
    st.text_area("Business context", key="business_context_text", height=140)

    if st.button("Run Assessment"):
        try:
            report = _run_assessment(mode)
        except Exception as exc:  # keep user edits; never crash the demo
            st.error(f"Run failed: {type(exc).__name__}: {exc}")
            report = None
        if report is not None:
            st.session_state.last_report = report

    report = st.session_state.last_report
    if report is not None:
        _render_badge(ui_formatters.format_readiness_badge(report.readiness_state))
        _render_timeline(report)
        _render_red_blue(report)
        _render_evidence(report)


if __name__ == "__main__":
    main()

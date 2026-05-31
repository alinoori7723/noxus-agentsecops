"""Full-width local Streamlit demo UI for Noxus AgentSecOps.

This is the ONLY module allowed to import Streamlit. It contains no core logic:
it loads inputs, calls the accepted orchestrator, and renders report data through
the pure-Python helpers in ``ui_formatters``.

Run locally with:
    streamlit run src/noxus/ui_streamlit.py
"""

from __future__ import annotations

import html
import os
from pathlib import Path

import streamlit as st
import yaml

# Absolute imports so `streamlit run src/noxus/ui_streamlit.py` works (Streamlit
# executes this file as a script, where relative imports are unavailable).
from noxus import ui_formatters
from noxus.cli import _build_provider_from_env, _models_from_env
from noxus.constants import MAX_TUNING_ITERATIONS, SAFETY_RAIL_HEADING
from noxus.llm_provider import ProviderError
from noxus.orchestrator import run_readiness_assessment
from noxus.policy_loader import validate_policy

_SAMPLES = Path(__file__).resolve().parent / "samples"
_AGENT_ENV_VARS = [
    "NOXUS_LLM_BASE_URL",
    "NOXUS_LLM_API_KEY",
    "NOXUS_RED_MODEL",
    "NOXUS_JUDGE_MODEL",
    "NOXUS_TUNING_MODEL",
]


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


def _escape(value) -> str:
    return html.escape(str(value), quote=True)


def _chip(label: str, color: str = "neutral", *, quiet: bool = False) -> str:
    quiet_class = " nx-chip-quiet" if quiet else ""
    return (
        f'<span class="nx-chip nx-chip-{_escape(color)}{quiet_class}">'
        f"{_escape(label)}</span>"
    )


def _code_block(value: str, *, compact: bool = False) -> str:
    compact_class = " nx-code-compact" if compact else ""
    return f'<pre class="nx-code{compact_class}">{_escape(value)}</pre>'


def _metric_tile(label: str, value, detail: str = "", color: str = "neutral") -> str:
    detail_html = f'<div class="nx-metric-detail">{_escape(detail)}</div>' if detail else ""
    return (
        f'<div class="nx-metric-tile nx-metric-{_escape(color)}">'
        f'<div class="nx-metric-label">{_escape(label)}</div>'
        f'<div class="nx-metric-value">{_escape(value)}</div>'
        f"{detail_html}</div>"
    )


def _input_stat(label: str, text: str) -> str:
    line_count = 0 if not text else len(text.splitlines())
    return (
        f'<div class="nx-input-stat"><span>{_escape(label)}</span>'
        f"<strong>{line_count} lines</strong>"
        f"<small>{len(text):,} characters</small></div>"
    )


def _render_css() -> None:
    st.markdown(
        """
<style>
    :root {
        --nx-bg: #f5f7fb;
        --nx-ink: #0b1220;
        --nx-muted: #5b677a;
        --nx-soft: #e5eaf2;
        --nx-panel: #ffffff;
        --nx-panel-strong: #0f172a;
        --nx-amber: #d97706;
        --nx-red: #dc2626;
        --nx-green: #16a34a;
        --nx-blue: #2563eb;
    }

    html, body, [data-testid="stAppViewContainer"] {
        background: var(--nx-bg);
    }

    [data-testid="stHeader"] {
        background: rgba(245, 247, 251, 0.82);
        backdrop-filter: blur(10px);
    }

    .block-container {
        max-width: none !important;
        padding: 1.35rem 2.4rem 4rem !important;
    }

    h1, h2, h3, p, div, label {
        letter-spacing: 0;
    }

    div[data-testid="stVerticalBlock"] {
        gap: 0.85rem;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: #e9eef6;
        border: 1px solid #d7dfec;
        border-radius: 10px;
        padding: 5px;
    }

    .stTabs [data-baseweb="tab"] {
        height: 38px;
        border-radius: 8px;
        padding: 0 16px;
        color: #475569;
        font-weight: 750;
        background: transparent;
    }

    .stTabs [aria-selected="true"] {
        background: #ffffff;
        color: #0f172a;
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.10);
    }

    div[role="radiogroup"] {
        gap: 10px;
    }

    div[role="radiogroup"] label {
        border: 1px solid #d7dfec;
        background: #ffffff;
        border-radius: 10px;
        padding: 10px 14px;
        min-height: 46px;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
    }

    div.stButton > button {
        border-radius: 10px;
        border: 1px solid #cbd5e1;
        min-height: 44px;
        font-weight: 800;
        letter-spacing: 0;
    }

    div.stButton > button[kind="primary"] {
        background: #0f172a;
        border-color: #0f172a;
        color: #ffffff;
        box-shadow: 0 16px 34px rgba(15, 23, 42, 0.22);
    }

    div.stButton > button[kind="primary"]:hover {
        background: #111c32;
        border-color: #111c32;
    }

    .stTextArea textarea {
        min-height: 360px;
        border-radius: 12px;
        border: 1px solid #cbd5e1;
        background: #fbfdff;
        color: #0f172a;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.9rem;
        line-height: 1.55;
        padding: 16px;
        box-shadow: inset 0 1px 0 rgba(15, 23, 42, 0.03);
    }

    .stTextArea textarea:focus {
        border-color: #64748b;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }

    .nx-hero {
        position: relative;
        overflow: hidden;
        min-height: 250px;
        border: 1px solid #172033;
        border-radius: 16px;
        background:
            linear-gradient(135deg, rgba(15, 23, 42, 0.98), rgba(30, 41, 59, 0.96)),
            repeating-linear-gradient(90deg, rgba(148, 163, 184, 0.10) 0 1px, transparent 1px 80px);
        color: #f8fafc;
        padding: 38px 42px 34px;
        box-shadow: 0 30px 80px rgba(15, 23, 42, 0.22);
    }

    .nx-hero::after {
        content: "";
        position: absolute;
        inset: auto 36px 0 auto;
        width: 42%;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(245, 158, 11, 0.7));
    }

    .nx-hero-grid {
        position: relative;
        z-index: 1;
        display: grid;
        grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.75fr);
        gap: 34px;
        align-items: end;
    }

    .nx-demo-badge {
        display: inline-flex;
        width: fit-content;
        align-items: center;
        gap: 8px;
        border: 1px solid rgba(251, 191, 36, 0.48);
        background: rgba(146, 64, 14, 0.30);
        color: #fde68a;
        border-radius: 999px;
        padding: 7px 11px;
        font-size: 0.74rem;
        font-weight: 850;
        text-transform: uppercase;
    }

    .nx-title {
        margin: 16px 0 10px;
        font-size: clamp(2.6rem, 4vw, 4.9rem);
        line-height: 0.98;
        font-weight: 900;
        color: #ffffff;
    }

    .nx-subtitle {
        margin: 0;
        max-width: 920px;
        color: #e2e8f0;
        font-size: 1.17rem;
        line-height: 1.45;
    }

    .nx-scope-note {
        margin: 16px 0 0;
        max-width: 880px;
        color: #b6c2d2;
        font-size: 0.97rem;
        line-height: 1.45;
    }

    .nx-proof-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
    }

    .nx-proof-chip {
        border: 1px solid rgba(148, 163, 184, 0.28);
        background: rgba(15, 23, 42, 0.52);
        border-radius: 12px;
        padding: 13px 14px;
        color: #e5e7eb;
        font-size: 0.86rem;
        font-weight: 800;
        min-height: 52px;
        display: flex;
        align-items: center;
    }

    .nx-band {
        margin-top: 24px;
        border: 1px solid #d7dfec;
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.86);
        padding: 22px 24px;
        box-shadow: 0 18px 44px rgba(15, 23, 42, 0.07);
    }

    .nx-section-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 18px;
        margin: 30px 0 12px;
    }

    .nx-kicker {
        color: #64748b;
        font-size: 0.75rem;
        font-weight: 900;
        text-transform: uppercase;
    }

    .nx-heading {
        margin: 3px 0 0;
        color: var(--nx-ink);
        font-size: clamp(1.38rem, 1.6vw, 1.95rem);
        line-height: 1.16;
        font-weight: 900;
    }

    .nx-copy {
        margin: 6px 0 0;
        max-width: 920px;
        color: var(--nx-muted);
        font-size: 0.96rem;
        line-height: 1.5;
    }

    .nx-chip {
        display: inline-flex;
        align-items: center;
        width: fit-content;
        border-radius: 999px;
        border: 1px solid transparent;
        padding: 4px 9px;
        margin: 0 6px 6px 0;
        font-size: 0.73rem;
        line-height: 1.2;
        font-weight: 850;
        white-space: nowrap;
    }

    .nx-chip-quiet {
        font-weight: 750;
    }

    .nx-chip-green { color: #14532d; background: #dcfce7; border-color: #86efac; }
    .nx-chip-amber { color: #78350f; background: #fef3c7; border-color: #f59e0b; }
    .nx-chip-red { color: #7f1d1d; background: #fee2e2; border-color: #fca5a5; }
    .nx-chip-blue { color: #1e3a8a; background: #dbeafe; border-color: #93c5fd; }
    .nx-chip-neutral { color: #334155; background: #f1f5f9; border-color: #cbd5e1; }

    .nx-config-shell {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 300px;
        gap: 18px;
        align-items: start;
    }

    .nx-input-stat {
        border: 1px solid #d7dfec;
        background: #ffffff;
        border-radius: 12px;
        padding: 13px;
        margin-bottom: 10px;
    }

    .nx-input-stat span,
    .nx-metric-label {
        display: block;
        color: #64748b;
        font-size: 0.72rem;
        font-weight: 900;
        text-transform: uppercase;
    }

    .nx-input-stat strong {
        display: block;
        color: #0f172a;
        font-size: 1.18rem;
        line-height: 1.25;
        margin-top: 3px;
    }

    .nx-input-stat small {
        display: block;
        color: #64748b;
        margin-top: 2px;
    }

    .nx-run-grid {
        display: grid;
        grid-template-columns: minmax(0, 1.35fr) minmax(340px, 0.65fr);
        gap: 18px;
        align-items: stretch;
    }

    .nx-side-panel {
        border: 1px solid #d7dfec;
        background: #ffffff;
        border-radius: 14px;
        padding: 16px;
    }

    .nx-field-label {
        color: #475569;
        font-size: 0.74rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 9px;
    }

    .nx-status-line {
        border: 1px solid #d7dfec;
        border-left: 4px solid #94a3b8;
        background: #f8fafc;
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 12px;
    }

    .nx-status-line.nx-status-green {
        border-left-color: var(--nx-green);
        background: #f0fdf4;
        border-color: #bbf7d0;
    }

    .nx-status-line.nx-status-amber {
        border-left-color: var(--nx-amber);
        background: #fffbeb;
        border-color: #fde68a;
    }

    .nx-status-title {
        color: #0f172a;
        font-size: 0.95rem;
        font-weight: 850;
        line-height: 1.2;
        margin-bottom: 3px;
    }

    .nx-panel-title {
        color: #0f172a;
        font-size: 1.02rem;
        font-weight: 900;
        line-height: 1.2;
        margin-bottom: 7px;
    }

    .nx-muted {
        color: #64748b;
        font-size: 0.92rem;
        line-height: 1.45;
    }

    .nx-small {
        color: #64748b;
        font-size: 0.8rem;
        line-height: 1.45;
    }

    .nx-warning-panel {
        border: 1px solid #f59e0b;
        background: #fffbeb;
        border-radius: 14px;
        padding: 16px;
    }

    .nx-verdict {
        border-radius: 18px;
        border: 1px solid #d7dfec;
        background: #ffffff;
        overflow: hidden;
        box-shadow: 0 24px 64px rgba(15, 23, 42, 0.10);
    }

    .nx-verdict-grid {
        display: grid;
        grid-template-columns: minmax(0, 1.15fr) minmax(420px, 0.85fr);
    }

    .nx-verdict-main {
        padding: 28px 30px;
        border-left: 8px solid #64748b;
    }

    .nx-verdict-main.nx-verdict-amber { border-left-color: var(--nx-amber); background: #fffbeb; }
    .nx-verdict-main.nx-verdict-green { border-left-color: var(--nx-green); background: #f0fdf4; }
    .nx-verdict-main.nx-verdict-red { border-left-color: var(--nx-red); background: #fef2f2; }

    .nx-verdict-state {
        color: #0f172a;
        font-size: clamp(1.55rem, 2.5vw, 3.2rem);
        line-height: 1.03;
        font-weight: 950;
        margin: 12px 0 8px;
    }

    .nx-verdict-detail {
        color: #334155;
        font-size: 1rem;
        line-height: 1.5;
        max-width: 880px;
    }

    .nx-metric-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
        padding: 18px;
        background: #f8fafc;
        height: 100%;
    }

    .nx-metric-tile {
        border: 1px solid #d7dfec;
        background: #ffffff;
        border-radius: 13px;
        padding: 15px;
        min-height: 112px;
    }

    .nx-metric-green { border-top: 4px solid var(--nx-green); }
    .nx-metric-amber { border-top: 4px solid var(--nx-amber); }
    .nx-metric-red { border-top: 4px solid var(--nx-red); }
    .nx-metric-blue { border-top: 4px solid var(--nx-blue); }
    .nx-metric-neutral { border-top: 4px solid #64748b; }

    .nx-metric-value {
        color: #0f172a;
        font-size: 1.75rem;
        font-weight: 950;
        line-height: 1.1;
        margin-top: 6px;
        overflow-wrap: anywhere;
    }

    .nx-metric-detail {
        color: #64748b;
        font-size: 0.82rem;
        line-height: 1.35;
        margin-top: 6px;
    }

    .nx-flow {
        display: grid;
        grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 12px;
        position: relative;
    }

    .nx-flow-step {
        position: relative;
        border: 1px solid #d7dfec;
        background: #ffffff;
        border-radius: 14px;
        padding: 15px;
        min-height: 196px;
        box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
    }

    .nx-flow-step::after {
        content: "";
        position: absolute;
        top: 36px;
        right: -12px;
        width: 12px;
        height: 1px;
        background: #cbd5e1;
    }

    .nx-flow-step:last-child::after {
        display: none;
    }

    .nx-step-number {
        width: 30px;
        height: 30px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        background: #0f172a;
        color: #ffffff;
        font-weight: 900;
        font-size: 0.78rem;
        margin-bottom: 10px;
    }

    .nx-step-title {
        color: #0f172a;
        font-weight: 900;
        line-height: 1.18;
        min-height: 38px;
        margin-bottom: 7px;
    }

    .nx-step-copy {
        color: #475569;
        font-size: 0.84rem;
        line-height: 1.4;
        margin: 8px 0;
    }

    .nx-cockpit-grid {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
        gap: 18px;
        align-items: start;
    }

    .nx-team-panel {
        border: 1px solid #cbd5e1;
        border-radius: 18px;
        background: #ffffff;
        overflow: hidden;
        box-shadow: 0 24px 64px rgba(15, 23, 42, 0.09);
    }

    .nx-team-head {
        padding: 18px 20px;
        border-bottom: 1px solid #d7dfec;
        background: #0f172a;
        color: #f8fafc;
    }

    .nx-team-head-red { background: #211618; }
    .nx-team-head-blue { background: #101c2e; }

    .nx-team-title {
        font-size: 1.1rem;
        font-weight: 950;
        line-height: 1.25;
    }

    .nx-team-copy {
        color: #cbd5e1;
        font-size: 0.86rem;
        line-height: 1.45;
        margin-top: 6px;
    }

    .nx-team-body {
        padding: 16px;
        background: #fbfdff;
    }

    .nx-card {
        border: 1px solid #d7dfec;
        background: #ffffff;
        border-radius: 14px;
        padding: 15px;
        margin-bottom: 12px;
        box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
    }

    .nx-card-title {
        color: #0f172a;
        font-weight: 900;
        line-height: 1.25;
        margin-bottom: 8px;
        overflow-wrap: anywhere;
    }

    .nx-code-id {
        display: inline-flex;
        max-width: 100%;
        overflow-wrap: anywhere;
        color: #0f172a;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.8rem;
        background: #eef2f7;
        border: 1px solid #d7dfec;
        border-radius: 7px;
        padding: 2px 6px;
        margin-right: 6px;
    }

    .nx-code {
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        border: 1px solid #d7dfec;
        border-radius: 12px;
        background: #0f172a;
        color: #e2e8f0;
        padding: 13px 14px;
        margin: 10px 0 0;
        font-size: 0.82rem;
        line-height: 1.55;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    .nx-code-compact {
        max-height: 170px;
        overflow: auto;
    }

    .nx-evidence-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
    }

    .nx-risk-panel {
        border: 1px solid #f59e0b;
        border-radius: 18px;
        background: #fffbeb;
        padding: 22px;
        box-shadow: 0 18px 48px rgba(146, 64, 14, 0.12);
    }

    .nx-risk-grid {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(320px, 0.42fr);
        gap: 16px;
        align-items: start;
    }

    .nx-risk-item {
        border: 1px solid #fbbf24;
        background: #ffffff;
        border-radius: 13px;
        padding: 14px;
        margin-bottom: 10px;
    }

    .nx-safeguard-grid {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 12px;
    }

    .nx-empty {
        border: 1px dashed #94a3b8;
        background: #ffffff;
        border-radius: 16px;
        padding: 26px;
        color: #475569;
    }

    .nx-ready {
        border: 1px solid #d7dfec;
        background: #ffffff;
        border-radius: 18px;
        padding: 22px 24px;
        box-shadow: 0 18px 44px rgba(15, 23, 42, 0.07);
    }

    .nx-ready-head {
        margin-bottom: 16px;
    }

    .nx-ready-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 14px;
    }

    .nx-ready-step {
        border: 1px solid #d7dfec;
        background: #f8fafc;
        border-radius: 14px;
        padding: 16px 16px 18px;
    }

    @media (max-width: 900px) {
        .nx-ready-grid {
            grid-template-columns: 1fr;
        }
    }

    @media (max-width: 1280px) {
        .nx-hero-grid,
        .nx-verdict-grid,
        .nx-run-grid,
        .nx-risk-grid {
            grid-template-columns: 1fr;
        }
        .nx-flow,
        .nx-safeguard-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
    }

    @media (max-width: 900px) {
        .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        .nx-hero {
            padding: 28px 22px;
        }
        .nx-proof-grid,
        .nx-config-shell,
        .nx-cockpit-grid,
        .nx-evidence-grid,
        .nx-flow,
        .nx-safeguard-grid,
        .nx-metric-grid {
            grid-template-columns: 1fr;
        }
        .nx-flow-step::after {
            display: none;
        }
    }
</style>
""",
        unsafe_allow_html=True,
    )


def _section(kicker: str, title: str, copy: str = "") -> None:
    copy_html = f'<p class="nx-copy">{_escape(copy)}</p>' if copy else ""
    st.markdown(
        f"""
<div class="nx-section-head">
  <div>
    <div class="nx-kicker">{_escape(kicker)}</div>
    <div class="nx-heading">{_escape(title)}</div>
    {copy_html}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_header() -> None:
    proof_items = [
        "92 tests passing",
        f"MAX_TUNING_ITERATIONS = {MAX_TUNING_ITERATIONS}",
        "Pydantic contracts",
        "Deterministic patch engine",
        "Local JSONL audit export",
    ]
    proof_html = "".join(
        f'<div class="nx-proof-chip">{_escape(item)}</div>' for item in proof_items
    )
    st.markdown(
        f"""
<section class="nx-hero">
  <div class="nx-hero-grid">
    <div>
      <div class="nx-demo-badge">Local demo cockpit</div>
      <h1 class="nx-title">Noxus AgentSecOps</h1>
      <p class="nx-subtitle">Pre-production AI security readiness testing for enterprise LLM apps.</p>
      <p class="nx-scope-note">Not a runtime firewall. Not a certification engine. A bounded readiness loop before production.</p>
    </div>
    <div class="nx-proof-grid">{proof_html}</div>
  </div>
</section>
""",
        unsafe_allow_html=True,
    )


def _render_input_configuration() -> None:
    _section(
        "Configuration workspace",
        "Target inputs",
        "Edit the system prompt, policy, and business context. Samples initialize once and user edits survive reruns.",
    )
    left, right = st.columns([0.78, 0.22])
    with left:
        st.markdown(
            """
<div class="nx-band" style="margin-top: 0;">
  <div class="nx-panel-title">Assessment target</div>
  <div class="nx-muted">The current text is passed directly to the existing readiness workflow. Nothing is reset automatically.</div>
</div>
""",
            unsafe_allow_html=True,
        )
    with right:
        if st.button("Reset to samples", key="reset_inputs", use_container_width=True):
            st.session_state.system_prompt_text = _read_sample("system_prompt.txt")
            st.session_state.security_policy_yaml_text = _read_sample(
                "security_policy.yaml"
            )
            st.session_state.business_context_text = _read_sample(
                "business_context.md"
            )
            st.markdown(
                """
<div class="nx-warning-panel">
  <div class="nx-panel-title">Samples restored</div>
  <div class="nx-muted">The previous report remains available until the next run.</div>
</div>
""",
                unsafe_allow_html=True,
            )

    tabs = st.tabs(["System Prompt", "Security Policy YAML", "Business Context"])
    with tabs[0]:
        text_col, stat_col = st.columns([0.76, 0.24])
        with text_col:
            st.text_area(
                "System Prompt",
                key="system_prompt_text",
                height=390,
                label_visibility="collapsed",
            )
        with stat_col:
            st.markdown(
                _input_stat("System Prompt", st.session_state.system_prompt_text)
                + """
<div class="nx-side-panel">
  <div class="nx-panel-title">Prompt under test</div>
  <div class="nx-muted">Noxus evaluates this prompt before and after deterministic patch application.</div>
</div>
""",
                unsafe_allow_html=True,
            )
    with tabs[1]:
        text_col, stat_col = st.columns([0.76, 0.24])
        with text_col:
            st.text_area(
                "Security Policy YAML",
                key="security_policy_yaml_text",
                height=390,
                label_visibility="collapsed",
            )
        with stat_col:
            st.markdown(
                _input_stat(
                    "Security Policy", st.session_state.security_policy_yaml_text
                )
                + """
<div class="nx-side-panel">
  <div class="nx-panel-title">Policy controls</div>
  <div class="nx-muted">Malformed YAML is surfaced before the run. The accepted policy loader remains unchanged.</div>
</div>
""",
                unsafe_allow_html=True,
            )
    with tabs[2]:
        text_col, stat_col = st.columns([0.76, 0.24])
        with text_col:
            st.text_area(
                "Business Context",
                key="business_context_text",
                height=330,
                label_visibility="collapsed",
            )
        with stat_col:
            st.markdown(
                _input_stat("Business Context", st.session_state.business_context_text)
                + """
<div class="nx-side-panel">
  <div class="nx-panel-title">Documentation context</div>
  <div class="nx-muted">Business context is preserved in report metadata and does not drive deterministic decisions.</div>
</div>
""",
                unsafe_allow_html=True,
            )


def _missing_agent_env() -> list[str]:
    return [name for name in _AGENT_ENV_VARS if not os.environ.get(name)]


_MODE_OPTIONS = ["Deterministic Mode", "Agent-Assisted Mode"]
_MODE_CAPTIONS = {
    "deterministic": (
        "The clean judge path. No credentials required. Runs the deterministic "
        "evaluator and patch engine end-to-end and is fully reproducible."
    ),
    "agent_assisted": (
        "Uses the existing env-var LLM provider for the red/judge/tuning agents. "
        "Agents only propose schema-bound changes; the deterministic engine still "
        "applies them."
    ),
}


def _select_mode() -> str:
    """Render a segmented mode selector (radio fallback) and return the mode key."""
    segmented = getattr(st, "segmented_control", None)
    if segmented is not None:
        label = segmented(
            "Assessment mode",
            _MODE_OPTIONS,
            default=_MODE_OPTIONS[0],
            key="assessment_mode",
            label_visibility="collapsed",
        )
    else:  # older Streamlit: horizontal radio still reads as a segmented control
        label = st.radio(
            "Assessment mode",
            _MODE_OPTIONS,
            index=0,
            horizontal=True,
            key="assessment_mode",
            label_visibility="collapsed",
        )
    # segmented_control can return None if the user deselects; default to first.
    if not label:
        label = _MODE_OPTIONS[0]
    return "agent_assisted" if label.startswith("Agent") else "deterministic"


def _render_run_controls() -> tuple[str, bool]:
    _section(
        "Assessment controls",
        "Run the readiness loop",
        "Pick an execution path, then run the bounded Red Team / Blue Team loop. "
        "Both modes preserve the deterministic evaluator and patch-engine boundaries.",
    )

    with st.container(border=True):
        control_col, action_col = st.columns([0.62, 0.38], gap="large")
        with control_col:
            st.markdown('<div class="nx-field-label">Execution mode</div>', unsafe_allow_html=True)
            mode = _select_mode()
            st.markdown(
                f'<p class="nx-muted" style="margin-top:10px;">{_escape(_MODE_CAPTIONS[mode])}</p>',
                unsafe_allow_html=True,
            )

        missing = _missing_agent_env() if mode == "agent_assisted" else []
        with action_col:
            if mode == "agent_assisted" and missing:
                missing_html = " ".join(_chip(name, "amber") for name in missing)
                st.markdown(
                    f"""
<div class="nx-status-line nx-status-amber">
  <div class="nx-status-title">Agent configuration needed</div>
  <div class="nx-small">Set these environment variables before running Agent-Assisted Mode:</div>
  <div style="margin-top: 8px;">{missing_html}</div>
</div>
""",
                    unsafe_allow_html=True,
                )
            else:
                ready_copy = (
                    "Deterministic path — no credentials required."
                    if mode == "deterministic"
                    else "All expected agent environment variables are present."
                )
                st.markdown(
                    f"""
<div class="nx-status-line nx-status-green">
  <div class="nx-status-title">Ready to assess</div>
  <div class="nx-small">{_escape(ready_copy)}</div>
</div>
""",
                    unsafe_allow_html=True,
                )
            run_clicked = st.button(
                "Run Assessment",
                key="run_assessment",
                type="primary",
                disabled=bool(missing),
                use_container_width=True,
            )
    return mode, run_clicked


def _render_readiness_summary(report) -> None:
    _section(
        "Readiness summary",
        "Final verdict",
        "The state below is rendered directly from the generated report. Conditional results stay conditional.",
    )
    model = ui_formatters.build_readiness_summary_model(report)
    badge = model["badge"]
    metric_html = (
        '<div class="nx-metric-grid">'
        + _metric_tile(
            "Before score",
            f"{model['before_score']}/100",
            f"{model['before_summary']['failed_probes']} failed probes",
            "red" if model["before_summary"]["failed_probes"] else "green",
        )
        + _metric_tile(
            "After score",
            f"{model['after_score']}/100",
            f"delta {model['score_delta']:+}",
            badge["color"],
        )
        + _metric_tile(
            "Open risks",
            model["open_risk_count"],
            "visible in report",
            "amber" if model["open_risk_count"] else "green",
        )
        + _metric_tile(
            "Human review",
            model["human_review_count"],
            "required categories",
            "amber" if model["human_review_count"] else "neutral",
        )
        + "</div>"
    )
    st.markdown(
        f"""
<section class="nx-verdict">
  <div class="nx-verdict-grid">
    <div class="nx-verdict-main nx-verdict-{_escape(badge["color"])}">
      <div>{_chip(badge["state"], badge["color"])}</div>
      <div class="nx-verdict-state">{_escape(badge["headline"])}</div>
      <div class="nx-verdict-detail">{_escape(badge["explanation"])}</div>
      <div style="margin-top: 14px;">
        {_chip(f"mode: {model['mode']}", "neutral", quiet=True)}
        {_chip(f"tuning iterations: {model['tuning_iterations']}", "neutral", quiet=True)}
      </div>
    </div>
    {metric_html}
  </div>
</section>
""",
        unsafe_allow_html=True,
    )


def _render_timeline(report) -> None:
    _section(
        "Audit timeline",
        "Six-step readiness flow",
        "The process flow uses only report fields: baseline, findings, patch proposal, deterministic application, retest, and readiness.",
    )
    cards = []
    for entry in ui_formatters.build_demo_timeline_model(report):
        cards.append(
            f"""
<div class="nx-flow-step">
  <div class="nx-step-number">{_escape(entry["step"])}</div>
  <div class="nx-step-title">{_escape(entry["label"])}</div>
  <div>{_chip(entry["status"], entry["status_color"])}</div>
  <div class="nx-step-copy">{_escape(entry["description"])}</div>
  <div class="nx-small"><strong>{_escape(entry["evidence_count"])}</strong> evidence items</div>
  <div class="nx-small">{_escape(entry["detail"])}</div>
</div>
"""
        )
    st.markdown(
        f'<section class="nx-flow">{"".join(cards)}</section>',
        unsafe_allow_html=True,
    )


def _probe_card(probe: dict) -> str:
    evidence = "".join(_code_block(item, compact=True) for item in probe["evidence"])
    if not evidence:
        evidence = '<div class="nx-small">No findings emitted for this probe.</div>'
    return f"""
<div class="nx-card">
  <div class="nx-card-title"><span class="nx-code-id">{_escape(probe["probe_id"])}</span>{_escape(probe["probe_type"])}</div>
  <div>
    {_chip(probe["status"], probe["status_color"])}
    {_chip(probe["detection_label"], probe["detection_color"])}
    {_chip(f"{probe['num_findings']} findings", "neutral")}
  </div>
  {evidence}
</div>
"""


def _patch_card(patch: dict) -> str:
    tone = "green" if patch["is_safety_rail"] else "neutral"
    return f"""
<div class="nx-card">
  <div class="nx-card-title"><span class="nx-code-id">{_escape(patch["operation"])}</span></div>
  <div>
    {_chip(patch["target"], "blue")}
    {_chip(patch["detail"] or "no detail", tone)}
  </div>
  <div class="nx-small">Source finding: {_escape(patch["source_finding"] or "not specified")}</div>
</div>
"""


def _render_red_blue(report) -> None:
    _section(
        "Red Team / Blue Team",
        "Security audit cockpit",
        "This is the core loop: Red Team evidence drives structured patch operations, and deterministic enforcement applies allowed changes.",
    )
    model = ui_formatters.build_red_blue_dashboard_model(report)
    red = model["red"]
    blue = model["blue"]
    red_metrics = (
        _chip(f"baseline failures: {red['before_summary']['failed_probes']}", "red")
        + _chip(f"retest failures: {red['after_summary']['failed_probes']}", "amber")
        + _chip(f"retest findings: {red['after_summary']['findings']}", "neutral")
    )
    blue_metrics = (
        _chip(f"patch operations: {len(blue['patches'])}", "blue")
        + _chip("deterministic engine", "green")
        + _chip(f"human review: {len(blue['human_review_requirements'])}", "amber")
    )
    baseline_html = "".join(_probe_card(p) for p in red["baseline_probes"])
    retest_html = "".join(_probe_card(p) for p in red["retest_probes"])
    patch_html = "".join(_patch_card(p) for p in blue["patches"])
    preview = blue["safety_rail_preview"]
    preview_html = (
        _chip(f"{SAFETY_RAIL_HEADING} real telemetry", "green")
        + _code_block(preview)
        if SAFETY_RAIL_HEADING in preview
        else f'<div class="nx-small">{_escape(preview)}</div>'
    )
    review_html = "".join(
        f'<div class="nx-risk-item">{_chip("human review", "amber")}{_escape(req)}</div>'
        for req in blue["human_review_requirements"]
    )
    if not review_html:
        review_html = '<div class="nx-small">No human-review categories reported.</div>'

    # Emit flat (no >=4-space indentation) so Streamlit's markdown pass does not
    # mistake the structural HTML for an indented code block and dump it as text.
    st.markdown(
        '<section class="nx-cockpit-grid">'
        '<div class="nx-team-panel">'
        '<div class="nx-team-head nx-team-head-red">'
        f'<div class="nx-team-title">{_escape(red["title"])}</div>'
        '<div class="nx-team-copy">Probe outcomes, detection modes, pass/fail state, and evidence snippets.</div>'
        f'<div style="margin-top: 12px;">{red_metrics}</div>'
        "</div>"
        '<div class="nx-team-body">'
        '<div class="nx-kicker">Before-state failures</div>'
        f"{baseline_html}"
        '<div class="nx-kicker" style="margin-top: 16px;">Retest probes</div>'
        f"{retest_html}"
        "</div></div>"
        '<div class="nx-team-panel">'
        '<div class="nx-team-head nx-team-head-blue">'
        f'<div class="nx-team-title">{_escape(blue["title"])}</div>'
        f'<div class="nx-team-copy">{_escape(blue["patch_engine_note"])}</div>'
        f'<div style="margin-top: 12px;">{blue_metrics}</div>'
        "</div>"
        '<div class="nx-team-body">'
        '<div class="nx-kicker">Patch operations</div>'
        f"{patch_html}"
        '<div class="nx-kicker" style="margin-top: 16px;">Safety rail preview</div>'
        f'<div class="nx-card">{preview_html}</div>'
        '<div class="nx-kicker" style="margin-top: 16px;">Human review requirements</div>'
        f"{review_html}"
        "</div></div>"
        "</section>",
        unsafe_allow_html=True,
    )


def _finding_card(finding: dict, *, open_risk: bool) -> str:
    confidence = (
        _chip(f"confidence: {finding['confidence']}", "blue")
        if finding["confidence"]
        else ""
    )
    open_risk_chip = _chip("open risk", "red") if open_risk else ""
    return f"""
<div class="nx-card">
  <div class="nx-card-title">{_escape(finding["finding_type"])}</div>
  <div>
    {_chip(finding["severity"], finding["severity_color"])}
    {_chip(finding["detection_label"], finding["detection_color"])}
    {_chip(finding["probe_id"], "neutral")}
    {confidence}
    {open_risk_chip}
  </div>
  <div class="nx-small">Remediation target: {_escape(finding["remediation_target_label"])}</div>
  <div class="nx-small">Evidence source: {_escape(finding["evidence_source"])}</div>
  {_code_block(finding["evidence"], compact=True)}
</div>
"""


def _render_evidence(report) -> None:
    _section(
        "Evidence report",
        "Findings with remediation context",
        "Severity, detection mode, evidence, confidence, and remediation targets are separated for quick review.",
    )
    model = ui_formatters.build_evidence_report_model(report)
    before_html = "".join(
        _finding_card(finding, open_risk=False)
        for finding in model["before_findings"]
    ) or '<div class="nx-empty">No before-state findings in this report.</div>'
    after_html = "".join(
        _finding_card(finding, open_risk=True) for finding in model["after_findings"]
    ) or '<div class="nx-empty">No retest findings in this report.</div>'
    before_tab, after_tab = st.tabs(["Before-state findings", "Retest findings"])
    with before_tab:
        st.markdown(
            f'<section class="nx-evidence-grid">{before_html}</section>',
            unsafe_allow_html=True,
        )
    with after_tab:
        st.markdown(
            f'<section class="nx-evidence-grid">{after_html}</section>',
            unsafe_allow_html=True,
        )


def _render_open_risks(report) -> None:
    _section(
        "Open Risks / Human Review",
        "Unresolved risk remains visible",
        "Noxus keeps unsupported proprietary-context exposure in front of the reviewer instead of cosmetically promoting the output.",
    )
    model = ui_formatters.build_evidence_report_model(report)
    risks_html = "".join(
        f'<div class="nx-risk-item">{_chip("open risk", "red")}'
        f'<div class="nx-muted">{_escape(risk)}</div></div>'
        for risk in model["open_risks"]
    ) or '<div class="nx-risk-item"><div class="nx-muted">No open risks reported.</div></div>'
    review_html = "".join(
        f'<div class="nx-risk-item">{_chip("human review", "amber")}'
        f'<div class="nx-muted">{_escape(req)}</div></div>'
        for req in model["human_review_requirements"]
    ) or '<div class="nx-risk-item"><div class="nx-muted">No human review categories reported.</div></div>'
    proprietary = (
        '<div class="nx-warning-panel">'
        '<div class="nx-panel-title">Proprietary-context exposure is not auto-patched</div>'
        f'<div class="nx-muted">{_escape(model["proprietary_context_explanation"])}</div>'
        "</div>"
        if model["proprietary_context_exposure_unresolved"]
        else ""
    )
    # Emit flat (no leading indentation): Streamlit's markdown pass treats
    # >=4-space-indented HTML as a code block and would dump it as raw text.
    st.markdown(
        '<section class="nx-risk-panel"><div class="nx-risk-grid">'
        '<div><div class="nx-panel-title">Open risks</div>'
        f"{risks_html}{proprietary}</div>"
        '<div><div class="nx-panel-title">Human review</div>'
        f"{review_html}</div>"
        "</div></section>",
        unsafe_allow_html=True,
    )


def _render_engineering_safeguards() -> None:
    _section(
        "Engineering safeguards",
        "Trust boundaries",
        "Concise implementation proof points for reviewers evaluating product scope and safety.",
    )
    cards = []
    for item in ui_formatters.build_engineering_safeguards_model():
        cards.append(
            f"""
<div class="nx-card">
  <div>{_chip(item["tone"].upper(), item["tone"])}</div>
  <div class="nx-card-title">{_escape(item["title"])}</div>
  <div class="nx-muted">{_escape(item["detail"])}</div>
</div>
"""
        )
    st.markdown(
        f'<section class="nx-safeguard-grid">{"".join(cards)}</section>',
        unsafe_allow_html=True,
    )


def _render_empty_demo_state() -> None:
    _section(
        "Ready to run",
        "The cockpit fills with real data after an assessment",
        "Nothing below is prefilled or synthesized. Click Run Assessment to generate "
        "a local report from the current inputs — these three steps run in order.",
    )
    steps = [
        (
            "Run baseline probes",
            "Red Team probes run against the original target and capture "
            "evidence-backed findings.",
        ),
        (
            "Apply structured remediation if needed",
            "Agents propose schema-bound patches; only the deterministic engine "
            "applies the allowed changes.",
        ),
        (
            "Retest and report open risks",
            "Probes rerun against the patched target. Unresolved risk stays visible "
            "— CONDITIONAL_PASS, never a fake PASS.",
        ),
    ]
    cards = "".join(
        f"""
<div class="nx-ready-step">
  <div class="nx-step-number">{i}</div>
  <div class="nx-step-title">{_escape(title)}</div>
  <div class="nx-step-copy">{_escape(copy)}</div>
</div>
"""
        for i, (title, copy) in enumerate(steps, start=1)
    )
    st.markdown(
        f"""
<section class="nx-ready">
  <div class="nx-ready-head">
    <div class="nx-status-title">No report generated yet</div>
    <div class="nx-muted">Deterministic Mode needs no credentials and is fully reproducible.</div>
  </div>
  <div class="nx-ready-grid">{cards}</div>
</section>
""",
        unsafe_allow_html=True,
    )


def _run_assessment(mode: str):
    raw_policy = yaml.safe_load(st.session_state.security_policy_yaml_text) or {}
    validate_policy(raw_policy)  # surface malformed policy early

    if mode == "agent_assisted":
        try:
            provider = _build_provider_from_env()
        except ProviderError as exc:
            st.markdown(
                f"""
<div class="nx-warning-panel">
  <div class="nx-panel-title">Agent-Assisted Mode unavailable</div>
  <div class="nx-muted">{_escape(exc)}</div>
  <div class="nx-small">Your edits are preserved. Switch to Deterministic Mode to run without credentials.</div>
</div>
""",
                unsafe_allow_html=True,
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
    _render_css()
    _render_header()

    _render_input_configuration()
    mode, run_clicked = _render_run_controls()

    if run_clicked:
        with st.spinner("Running readiness assessment..."):
            try:
                report = _run_assessment(mode)
            except Exception as exc:  # keep user edits; never crash the demo
                st.markdown(
                    f"""
<div class="nx-warning-panel">
  <div class="nx-panel-title">Run failed</div>
  <div class="nx-muted">{_escape(type(exc).__name__)}: {_escape(exc)}</div>
</div>
""",
                    unsafe_allow_html=True,
                )
                report = None
            if report is not None:
                st.session_state.last_report = report

    report = st.session_state.last_report
    if report is not None:
        _render_readiness_summary(report)
        _render_timeline(report)
        _render_red_blue(report)
        _render_evidence(report)
        _render_open_risks(report)
        _render_engineering_safeguards()
    else:
        _render_empty_demo_state()


if __name__ == "__main__":
    main()

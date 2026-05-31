# Noxus AgentSecOps — AI Security Readiness Tester for LLM Apps

Noxus AgentSecOps is a **pre-production AI security readiness tester**. It runs an
autonomous **attack → evaluate → patch → retest** loop against a target LLM app's
system prompt and security policy, then produces an **evidence-backed readiness
report**. A deterministic core guarantees reproducibility; an optional
schema-bound agent layer (Red Team → Semantic Judge → Policy Tuning) adds
LLM-driven probing and tuning while a deterministic engine remains the only thing
that ever applies a patch.

It is **not** a runtime firewall, a DLP replacement, a compliance certification
engine, a production traffic gateway, or a replacement for Google security
products. It is a repeatable way to validate and tune prompt/policy security
*before* production, with honest results.

All four engineering milestones are complete and accepted (deterministic
skeleton → agent layer → demo UI → container packaging), backed by **91+ passing
tests**.

| Layer                    | Status       |
| ------------------------ | ------------ |
| Deterministic evaluator  | Complete     |
| Agent layer              | Complete     |
| Demo UI                  | Complete     |
| Docker packaging         | Complete     |
| Audit export             | Local JSONL  |
| Runtime gateway          | Out of scope |
| Compliance certification | Out of scope |

## Judge Quickstart — 3 Minute Run

**A. Build the Docker image**

```bash
docker build -t noxus-agentsecops:local .
```

**B. Run the local Streamlit demo**

```bash
docker run --rm -p 8501:8501 \
  -e NOXUS_STREAMLIT_PORT=8501 \
  noxus-agentsecops:local
```

Then open http://localhost:8501, keep **Deterministic Mode**, and click
**Run Assessment**.

**C. Deterministic CLI smoke (no credentials needed)**

```bash
docker run --rm noxus-agentsecops:local \
  noxus run --mode deterministic \
    --system-prompt src/noxus/samples/system_prompt.txt \
    --policy src/noxus/samples/security_policy.yaml \
    --business-context src/noxus/samples/business_context.md
```

**D. Optional local audit export (opt-in, local file only)**

```bash
mkdir -p outputs/audit
PYTHONPATH=src python3 -m noxus.cli run \
  --mode deterministic \
  --system-prompt src/noxus/samples/system_prompt.txt \
  --policy src/noxus/samples/security_policy.yaml \
  --business-context src/noxus/samples/business_context.md \
  --audit-jsonl-output outputs/audit/readiness_reports.jsonl
```

**E. Optional agent-assisted mode (local LiteLLM-compatible endpoint)**

```bash
export NOXUS_LLM_BASE_URL="http://localhost:4000/v1"
export NOXUS_LLM_API_KEY="<your-local-litellm-key>"
export NOXUS_RED_MODEL="gemini-3.5-flash"
export NOXUS_JUDGE_MODEL="gemini-3.5-flash"
export NOXUS_TUNING_MODEL="gemini-3.1-pro-preview"
```

### What you will see (and why)

- **What Noxus does:** it red-teams a target LLM app with structured probes,
  detects failures with evidence, proposes schema-bound policy/prompt patches,
  applies them through a deterministic engine, reruns the probes, and reports a
  before/after readiness verdict.
- **Why it is agentic:** in agent-assisted mode three bounded, schema-constrained
  agents close the loop — a Red Team Agent generates probes, a Semantic Judge
  evaluates the cases that need judgment, and a Policy Tuning Agent proposes
  patches — looping at most `MAX_TUNING_ITERATIONS = 2`. Agents only *propose*;
  the deterministic patch engine *applies*.
- **What the demo shows:** a deliberately weak policy fails first (including an
  indirect prompt-injection case labeled `[DETERMINISTIC SIMULATION]`), then a
  `[CRITICAL_SAFETY_RAILS]` block and policy fixes are applied, and the retest
  improves.
- **Why the final status is intentionally `CONDITIONAL_PASS`:** proprietary-context
  exposure has no approved auto-remediation, so it remains an honest, visible open
  risk. We never fake a `PASS` or hide open risks — an honest conditional result is
  more useful to a security reviewer than a green light that isn't earned.

### Evidence-driven engineering summary

- **91+ passing tests**, including **35 Milestone 1 deterministic/regression tests**.
- **Schema-bound Pydantic v2 contracts** for every LLM output (one bounded repair
  attempt; on failure → `SchemaContractError` → `HUMAN_REVIEW_REQUIRED`).
- **AST/static scope guard** that blocks forbidden cloud/provider imports and keeps
  Streamlit isolated to the UI module.
- **Deterministic patch engine** is the only component that mutates prompts/policy.
- **Bounded loop:** `MAX_TUNING_ITERATIONS = 2`.
- **Non-root Docker container** (`python:3.11-slim`, user `noxus_user`).
- **Local-only JSONL audit export** (opt-in; no network, no cloud SDK).

### Explicit scope honesty

Noxus is **not** a runtime firewall, **not** a compliance certification engine,
does **not** integrate a real BigQuery/Cloud SDK, and does **not** perform
production traffic interception. The JSONL audit export is plain local NDJSON that
*can* be ingested by external pipelines (including BigQuery) without embedding any
cloud SDK.

## What Milestone 1 implements

- `constants.py` — fixed project constants (incl. `MAX_TUNING_ITERATIONS = 2`).
- `schemas.py` — strict Pydantic v2 schemas + enums (policy, probe, finding,
  patch, report).
- `policy_loader.py` — load text files and YAML, validate the policy schema.
- `probe_registry.py` — a fixed registry of ≥5 deterministic probes.
- `target_simulator.py` — a deterministic mock target (no LLM) whose behavior
  changes after safety patches, so the retest loop can be validated.
- `evaluator.py` — `DeterministicEvaluator v0`: regex/marker-based, evidence-backed findings.
- `patch_mapper.py` — maps emitted findings to exact structured patch operations.
- `patch_engine.py` — applies patches deterministically (safety rail + policy edits).
- `report.py` — before/after readiness report + human-readable CLI rendering.
- `cli.py` — `noxus run ...` smoke flow.

## What Milestone 1 intentionally does NOT implement

No UI/frontend, no cloud deployment / Cloud Run, no BigQuery, no Gemini / Vertex
AI / Model Armor / Sensitive Data Protection, no real LLM gateway or runtime
firewall, no production traffic interception, no GitHub PR creation, no
multi-tenant SaaS, and **no compliance certification claims**. There are no
network or cloud calls of any kind.

## Important honesty notes

- **Indirect prompt injection is a deterministic simulation scaffold**, not the
  final semantic LLM judge. It is detected via fixed marker strings and is always
  labeled `[DETERMINISTIC SIMULATION]` in the CLI report. The `semantic_llm`
  detection mode exists in the schema for future compatibility only and is never
  executed in Milestone 1.
- **`business_context.md` is documentation-only.** It is loaded as raw text and
  attached to the report metadata (`business_context_used_for:
  documentation_only`). It does not drive any deterministic decision.
- **The target simulator changes its response after safety patches.** Once the
  `[CRITICAL_SAFETY_RAILS]` clause is present in the system prompt *or*
  `prompt_injection.detect_indirect_instructions` is `true`, the simulated target
  stops emitting the failure markers. This is not a hidden success bypass — it is
  the explicit, documented mechanism that lets the patch → retest loop be
  validated deterministically without any LLM call. Remaining findings (e.g.
  proprietary context exposure) are reported honestly as open risks.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run tests

```bash
pytest -q
```

## Run the CLI smoke demo

Using the installed console script:

```bash
noxus run \
  --system-prompt src/noxus/samples/system_prompt.txt \
  --policy src/noxus/samples/security_policy.yaml \
  --business-context src/noxus/samples/business_context.md
```

Or without installing (src-layout on the path):

```bash
PYTHONPATH=src python -m noxus.cli run \
  --system-prompt src/noxus/samples/system_prompt.txt \
  --policy src/noxus/samples/security_policy.yaml \
  --business-context src/noxus/samples/business_context.md
```

The before-state fails the `indirect_prompt_injection` deterministic simulation;
the after-state neutralizes it once `[CRITICAL_SAFETY_RAILS]` is inserted and
indirect-instruction detection is enabled in the policy.

## Milestone 2 — schema-bound agent layer

Milestone 2 adds an optional LLM agent layer **on top of** the accepted
deterministic skeleton. The deterministic evaluator and patch engine are never
replaced — agents only *propose* schema-bound objects, and the deterministic
patch engine remains the only component allowed to apply patches.

### Modes

Choose with `--mode` (default `deterministic`):

- `--mode deterministic` — behaves exactly like Milestone 1. No LLM, no
  network, no credentials required.
- `--mode agent-assisted` — layers three schema-bound agents over the
  deterministic loop:
  - **Red Team Agent** proposes a `list[Probe]` (must include at least one
    `indirect_prompt_injection` probe; this is mandated in the prompt template
    *and* enforced by the validation layer).
  - **Semantic Judge Agent** produces a `SemanticJudgment`
    (`detection_mode = semantic_llm`) that **supplements** — never erases — the
    deterministic findings. It can never turn proprietary-context exposure into
    a PASS.
  - **Policy Tuning Agent** proposes a `PatchSet`. It never applies patches;
    the deterministic patch engine does.

The deterministic baseline probes are always included as regression probes in
agent-assisted mode, and the tuning loop is bounded by
`MAX_TUNING_ITERATIONS = 2`.

### Required environment variables (real local LiteLLM usage)

Agent-assisted mode talks to a LiteLLM-compatible OpenAI-style
`/v1/chat/completions` endpoint using **only** the Python standard library
(`urllib`). No provider SDKs, no `requests`/`httpx`, no cloud clients.

- `NOXUS_LLM_BASE_URL` — base URL of the local LiteLLM endpoint (required)
- `NOXUS_LLM_API_KEY` — API key (required)
- `NOXUS_RED_MODEL` — Red Team model (default `gemini-3.5-flash`)
- `NOXUS_JUDGE_MODEL` — Semantic Judge model (default `gemini-3.5-flash`)
- `NOXUS_TUNING_MODEL` — Policy Tuning model (default `gemini-3.1-pro-preview`)

Model names are configurable strings only; there is no provider-specific product
logic. If the required env vars are missing in agent-assisted mode, the CLI exits
non-zero with a clear error. Deterministic mode never requires them.

```bash
PYTHONPATH=src python3 -m noxus.cli run \
  --mode agent-assisted \
  --system-prompt src/noxus/samples/system_prompt.txt \
  --policy src/noxus/samples/security_policy.yaml \
  --business-context src/noxus/samples/business_context.md
```

### Schema contracts, repair, and the HUMAN_REVIEW_REQUIRED fallback

- **Tests never make real network calls.** They drive a `FakeLLMProvider`.
- **All LLM outputs are schema-bound and validated** against strict Pydantic
  schemas before use.
- **One repair attempt maximum.** If a model returns malformed JSON or an object
  that fails schema validation, exactly one bounded repair is requested. There is
  no second repair.
- **`SchemaContractError` bubbles to the orchestrator.** Agents must not suppress
  it or continue with partial state. The `run_readiness_assessment` orchestrator
  catches it, immediately stops all further LLM execution for that run, applies
  no patches, and returns a `ReadinessReport` with
  `readiness_state = HUMAN_REVIEW_REQUIRED` plus an open risk identifying the
  failing stage. Already-collected deterministic evidence is preserved.

### Static scope guard

`tests/test_scope_guard.py` statically scans **only production code** under
`src/noxus/**/*.py` (via `ast`, inspecting `ast.Import` / `ast.ImportFrom` nodes
only — comments, docstrings, and string literals are ignored) plus the
`pyproject.toml` dependency metadata. It does not scan `tests/`, `.venv/`,
third-party internals, the README, or generated files. It fails the build if any
forbidden out-of-scope module or dependency (e.g. `vertexai`, `google.cloud`,
`langgraph`, `fastapi`, `requests`, `httpx`, `openai`, `anthropic`,
`google.generativeai`, `google.genai`, `boto3`) appears.

## Milestone 3 — local demo UI & report presentation

Milestone 3 adds a **presentation layer only**. It does not change any core
behavior: the deterministic evaluator, the agents, the patch engine, and the
orchestrator are all unchanged. It adds a full-width local Streamlit demo plus
pure-Python formatting helpers so a reviewer can understand the
attack → evaluate → patch → retest loop at a glance.

### Run the demo UI

```bash
pip install -e ".[dev]"   # installs streamlit (the only new runtime dependency)
streamlit run src/noxus/ui_streamlit.py
```

The UI lets you pick a mode, edit the target system prompt / security policy
YAML / business context, run an assessment, and view the iteration timeline, a
Red Team / Blue Team cockpit, and an evidence report.

- **Deterministic Mode** (default) reproduces Milestone 1/2 deterministic
  behavior and needs **no model credentials**.
- **Agent-Assisted Mode** uses the existing env-var provider configuration
  (`NOXUS_LLM_BASE_URL`, `NOXUS_LLM_API_KEY`, and the `NOXUS_*_MODEL` names). If
  those env vars are missing, the UI shows a clear warning and does **not** crash
  or wipe your edits.

### Manual UI smoke checklist

Use this short screen-recording pass before judging or demo submission:

- Open the Streamlit UI with `streamlit run src/noxus/ui_streamlit.py`.
- Confirm the pre-run **Ready to run** panel shows the three-step loop (baseline
  probes → structured remediation → retest and report open risks).
- Keep **Deterministic Mode** selected in the segmented control and click **Run Assessment**.
- Confirm `[DETERMINISTIC SIMULATION]` is visible in the Red Team / evidence views.
- Confirm `[CRITICAL_SAFETY_RAILS]` is visible in the Blue Team safety-rail preview.
- Confirm the final readiness card shows `CONDITIONAL_PASS`, not `PASS`.
- Confirm proprietary-context exposure appears under **Open Risks / Human Review**.
- Edit an input, click **Run Assessment**, and confirm the edit survives rerun.
- Confirm there is no fake `PASS` and no hidden open-risk state.

### Honest presentation guarantees

- The UI is a **local demo presentation only**. Noxus is a **pre-production
  readiness tester, not a runtime firewall**, and makes **no compliance
  certification claims**.
- `CONDITIONAL_PASS` with an open risk is **intentional and honest** — it is
  shown in amber and is never cosmetically promoted to `PASS`.
- **Proprietary-context exposure stays a visible, unresolved open risk** (it has
  no approved auto-remediation in these milestones).
- Honest labels are always shown: `[DETERMINISTIC SIMULATION]`,
  `[SEMANTIC LLM JUDGMENT]` (with the judge's confidence), and
  `[DETERMINISTIC CHECK]`. Open risks are never hidden.

### Architecture / isolation notes

- **`ui_formatters.py` is pure Python and view-framework-free.** It contains no
  Streamlit imports, type hints, hooks, or references at all, and is fully
  unit-testable without a browser. The UI's timeline and dashboard are built from
  **real structured report data**, never from hardcoded demo values.
- **Streamlit is isolated to `src/noxus/ui_streamlit.py`** — the only module
  permitted to import it. `tests/test_ui_scope_guard.py` enforces this statically
  (AST import nodes only) and verifies that `streamlit` is the only new runtime
  dependency in `pyproject.toml`.
- **`st.session_state` persists your edits.** The keys `system_prompt_text`,
  `security_policy_yaml_text`, `business_context_text`, and `last_report` are
  initialized from the sample files exactly once, so edits and prior results
  survive Streamlit reruns (including clicking *Run Assessment*).
- Tests never start a Streamlit server or a browser — only the pure formatters
  and the static import boundaries are tested.

## Milestone 4 — packaging & container readiness

Milestone 4 is **packaging and infrastructure-readiness only** — it changes no
product logic. It adds a Docker image, a `.dockerignore`, and an optional,
**opt-in, local-file-only** JSONL audit export.

> Noxus is a pre-production readiness tester — **not a runtime firewall** and
> **not a compliance certification engine**. No cloud SDKs (BigQuery, Cloud
> Storage, Vertex, etc.) are included; the audit export is plain local NDJSON.

### Build & run the container

```bash
docker build -t noxus-agentsecops:local .

# Start the local Streamlit demo UI (default command):
docker run --rm -p 8501:8501 \
  -e NOXUS_STREAMLIT_PORT=8501 \
  noxus-agentsecops:local
```

Override the Streamlit port:

```bash
docker run --rm -p 9000:9000 -e NOXUS_STREAMLIT_PORT=9000 noxus-agentsecops:local
```

Pass LLM env vars for agent-assisted mode (deterministic mode needs none):

```bash
docker run --rm -p 8501:8501 \
  -e NOXUS_LLM_BASE_URL=http://host.docker.internal:4000/v1 \
  -e NOXUS_LLM_API_KEY=sk-local \
  -e NOXUS_RED_MODEL=gemini-3.5-flash \
  -e NOXUS_JUDGE_MODEL=gemini-3.5-flash \
  -e NOXUS_TUNING_MODEL=gemini-3.1-pro-preview \
  noxus-agentsecops:local
```

Run the deterministic CLI inside the container (command override):

```bash
docker run --rm noxus-agentsecops:local \
  noxus run --mode deterministic \
    --system-prompt src/noxus/samples/system_prompt.txt \
    --policy src/noxus/samples/security_policy.yaml \
    --business-context src/noxus/samples/business_context.md
```

The image is based on `python:3.11-slim`, runs as the non-root user
`noxus_user`, sets `PYTHONDONTWRITEBYTECODE=1` / `PYTHONUNBUFFERED=1`, and copies
only `pyproject.toml`, `README.md`, and `src/`. `.dockerignore` keeps
`.git/`, `.venv/`, caches, `outputs/`, `reports/`, `tmp/`, `*.log`, `.env*`, and
`tests/` out of the image (while keeping `src/`, `pyproject.toml`, `README.md`,
and the sample files).

### Optional local JSONL audit export (opt-in)

Audit export is **off by default** — no file is written unless you explicitly
pass the flag. It is local-file only and cloud-agnostic (no BigQuery, no Cloud
SDK, no network sink).

```bash
mkdir -p outputs/audit
PYTHONPATH=src python3 -m noxus.cli run \
  --mode deterministic \
  --system-prompt src/noxus/samples/system_prompt.txt \
  --policy src/noxus/samples/security_policy.yaml \
  --business-context src/noxus/samples/business_context.md \
  --audit-jsonl-output outputs/audit/readiness_reports.jsonl
```

This appends (never overwrites) one JSON line per run. Each line has stable
top-level fields (`schema_version`, `exported_at_utc`, `readiness_state`,
`before_score`, `after_score`, `probe_count`, `finding_count`,
`open_risk_count`) plus the full `report` object — valid newline-delimited JSON
suitable for downstream ingestion. You can also call it as a library:

```python
from noxus.audit_export import append_audit_jsonl
append_audit_jsonl(report, "outputs/audit/readiness_reports.jsonl")
```

Docker builds are documented and manually runnable; the automated tests validate
the Dockerfile/.dockerignore **statically** and never require Docker, a network,
cloud credentials, or a running Streamlit server.

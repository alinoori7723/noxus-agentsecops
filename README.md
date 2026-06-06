# Noxus AgentSecOps — AI Security Readiness Tester for LLM Apps

Noxus AgentSecOps is a **pre-production AI security readiness tester**. It runs an
autonomous **attack → evaluate → patch → retest** loop against a target LLM app's
system prompt and security policy, then produces an **evidence-backed readiness
report**. A deterministic core guarantees reproducibility; an optional
schema-bound agent layer (Red Team → Semantic Judge → Policy Tuning) adds
LLM-driven probing and tuning while a deterministic engine remains the only thing
that ever applies a patch.

**Positioning:** Noxus is a bounded agentic audit and remediation-readiness loop.
It proposes schema-bound remediations, applies only deterministic allowed patches,
measures which findings were resolved, and refuses to mark the target safe when
unsupported risks remain.

It is **not** a runtime firewall, a DLP replacement, a compliance certification
engine, a production traffic gateway, or a replacement for Google security
products. It does not fully autonomously remediate or automatically secure the
target — the deterministic engine applies only allowed, lineage-linked patches,
and unresolved risks stay open for human review. It is a repeatable way to
validate and tune prompt/policy security *before* production, with honest results.

All engineering milestones are complete and accepted (deterministic skeleton →
agent layer → demo UI → container packaging), and the UI has been rebuilt as a
production-grade **React/Tailwind cockpit** served by a minimal **FastAPI**
backend. Release verification: **457 Python tests** (plus **55 frontend tests**).

| Layer                    | Status       |
| ------------------------ | ------------ |
| Deterministic evaluator  | Complete     |
| Agent layer              | Complete     |
| React + FastAPI UI       | Complete     |
| Docker packaging         | Complete     |
| Audit export             | Local JSONL  |
| Runtime gateway          | Out of scope |
| Compliance certification | Out of scope |

## Judge Quickstart — 3 Minute Run

**A. Build the Docker image**

```bash
docker build -t noxus-agentsecops:react-local .
```

**B. Run the React cockpit (FastAPI serves the built SPA + the API)**

```bash
docker run --rm -p 8787:8787 \
  -e NOXUS_API_PORT=8787 \
  noxus-agentsecops:react-local
```

Then open http://localhost:8787, keep **Deterministic Mode**, and click
**Run Readiness Assessment**. Deterministic mode needs **no AI credentials**.

**C. Deterministic CLI smoke (no credentials needed)**

```bash
docker run --rm noxus-agentsecops:react-local \
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

- Release verification: **457 Python tests** (Python core + API; run via
  `pip install -e ".[dev]"` then `pytest -q`), including **35 Milestone 1
  deterministic/regression tests**, plus **55 frontend tests**.
- **Schema-bound Pydantic v2 contracts** for every LLM output (one bounded repair
  attempt; on failure → `SchemaContractError` → `HUMAN_REVIEW_REQUIRED`).
- **AST/static scope guard** that blocks forbidden cloud/provider imports and keeps
  the web framework isolated to `api_server.py`.
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

Install the test extras first — they include `httpx`, which `fastapi.testclient`
needs for the HTTP-level API tests. Without the extras those tests are skipped:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"   # pytest + httpx (test-only)
.venv/bin/pytest -q                 # full suite: release-verified at 457 Python tests
```

`httpx` is a **test-only** dependency (not a runtime dependency). Running
`pytest` without the dev extras (e.g. on a bare host without FastAPI/httpx)
honestly skips the HTTP-level API suite rather than reporting it as passing.

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

## Web UI — React cockpit + FastAPI backend

The presentation layer is a production-grade **React + TypeScript + Vite +
Tailwind** single-page app served by a minimal **FastAPI** backend. It changes
no core behavior: the deterministic evaluator, the agents, the patch engine, and
the orchestrator are all unchanged. The pure-Python `ui_formatters` display
models are reused by the API so honest-labeling rules live in exactly one place.

> The previous Streamlit UI has been fully removed from the runtime. `streamlit`
> is no longer a dependency.

### Architecture

- **`src/noxus/api_core.py`** — framework-free request/response logic, provider
  construction, API-key redaction, and assessment running. Fully unit-testable
  without a web server.
- **`src/noxus/api_server.py`** — the only module that imports the web framework.
  Thin FastAPI app exposing `/api/*` and serving the built React SPA.
- **`apps/web/`** — the React frontend (hand-crafted Tailwind components).

### Run in development (two processes)

```bash
# 1) Backend API (no AI credentials needed for deterministic mode)
pip install -e .
NOXUS_TEST_COUNT=457 uvicorn noxus.api_server:app --reload --port 8787

# 2) Frontend dev server (proxies /api to the backend)
cd apps/web
npm install
npm run dev          # http://localhost:5173
```

For a production-style single-origin run, build the SPA and let FastAPI serve it:

```bash
cd apps/web && npm run build && cd -
NOXUS_WEB_DIST=apps/web/dist NOXUS_TEST_COUNT=457 \
  uvicorn noxus.api_server:app --port 8787
# open http://localhost:8787
```

### API endpoints

| Method & path                | Purpose                                              |
| ---------------------------- | ---------------------------------------------------- |
| `GET  /api/health`           | `{ ok, product, mode }` liveness                     |
| `GET  /api/sample-inputs`    | Bundled sample system prompt / policy / context      |
| `GET  /api/proof`            | Non-secret proof indicators (test count, etc.)       |
| `POST /api/assessments/run`  | Run a deterministic or agent-assisted assessment     |
| `POST /api/audit/export-local` | Opt-in: append the report under the configured audit dir |

### Server configuration & hardening

| Env var                  | Default        | Purpose                                              |
| ------------------------ | -------------- | ---------------------------------------------------- |
| `NOXUS_API_PORT`         | `8787`         | uvicorn listen port.                                 |
| `NOXUS_WEB_DIST`         | auto-detected  | Built SPA directory to serve.                        |
| `NOXUS_AUDIT_DIR`        | `outputs/audit`| Directory the audit export is **confined** to.       |
| `NOXUS_ENABLE_DEV_CORS`  | _unset (off)_  | Set truthy to enable CORS — **local dev only**.      |
| `NOXUS_DEV_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowlist when dev CORS is on. |

Hardening notes:

- **CORS is OFF by default** and is **never a wildcard**. It is enabled only when
  `NOXUS_ENABLE_DEV_CORS` is truthy, and only for the explicit origin allowlist —
  intended for local development against the Vite dev server.
- **Static SPA serving is confined to the built directory.** Requested paths are
  resolved and checked for containment (no `..` traversal, no absolute paths); a
  request outside the static root returns `404`. Backend source, `pyproject.toml`,
  and `package.json` are never served.
- **Audit export never accepts a caller path.** `POST /api/audit/export-local`
  takes at most a sanitized `filename` (bare `*.jsonl`, no slashes/`..`) and
  always writes under `NOXUS_AUDIT_DIR`. Invalid names return `400`. It writes
  only when explicitly called.

### Provider configuration (Agent-Assisted Mode)

**Deterministic Mode** is the default judge path and requires **no provider and
no API key**. **Agent-Assisted Mode** sends a `provider_config` to the backend:

- **Local LLM / LiteLLM** (`local_openai_compatible`) — OpenAI-style gateway,
  default base URL `http://localhost:4000/v1`.
- **OpenAI-compatible** (`openai_compatible`) — any vendor exposing
  `/v1/chat/completions`; set the base URL.
- **Gemini native** (`gemini_native`) — Google Generative Language API via the
  standard library (no SDK). Model presets (`gemini-3.5-flash`,
  `gemini-3.1-pro-preview`, `gemini-3.1-flash-lite-preview`) are convenience
  defaults, **not availability claims** — any custom model ID can be typed.

### API key handling (privacy)

- The API key is entered in a **password field** and sent **only** in the POST
  body of `/api/assessments/run`, for **that one request**.
- The backend uses it **in memory** to build the provider, then discards it. It
  is **never** stored in reports, audit export, logs, the response, browser
  `localStorage`, or URL query params. Backend logs only redacted metadata.
- Deterministic mode never involves a key at all.

### Manual UI smoke checklist

Use this short screen-recording pass before judging or demo submission:

- Open the cockpit (dev `http://localhost:5173`, or built `http://localhost:8787`).
- Confirm the pre-run **Ready to run** panel shows the three-step loop (baseline
  probes → structured remediation → retest and report open risks).
- Keep **Deterministic Mode** selected and click **Run Readiness Assessment**.
- Confirm `[DETERMINISTIC SIMULATION]` is visible in the Red Team / evidence views.
- Confirm `[CRITICAL_SAFETY_RAILS]` is visible in the Blue Team safety-rail preview.
- Confirm the final readiness card shows `CONDITIONAL_PASS`, not `PASS`.
- Confirm proprietary-context exposure appears under **Open Risks / Human Review**.
- Switch to **Agent-Assisted Mode** and confirm the provider panel (provider type,
  password API-key field, model fields, Gemini presets + custom) and the in-memory
  key note are shown; with no key the Run button is disabled.
- Confirm there is no fake `PASS` and no hidden open-risk state.

### Honest presentation guarantees

- The UI is a **local demo presentation only**. Noxus is a **pre-production
  readiness tester, not a runtime firewall**, and makes **no compliance
  certification claims**.
- `CONDITIONAL_PASS` with an open risk is **intentional and honest** — shown in
  amber and never cosmetically promoted to `PASS`.
- **Proprietary-context exposure stays a visible, unresolved open risk** (it has
  no approved auto-remediation in these milestones).
- Honest labels are always shown: `[DETERMINISTIC SIMULATION]`,
  `[SEMANTIC LLM JUDGMENT]` (with the judge's confidence), and
  `[DETERMINISTIC CHECK]`. Open risks are never hidden.

### Architecture / isolation notes

- **`ui_formatters.py` is pure Python and view-framework-free**, reused by both
  the API and tests. Display data is built from **real structured report data**,
  never hardcoded demo values.
- **The web framework is isolated to `api_server.py`** — the only module allowed
  to import FastAPI. `api_core.py` stays framework-free.
  `tests/test_ui_scope_guard.py` enforces this statically and verifies the
  runtime dependency set (`pydantic`, `PyYAML`, `fastapi`, `uvicorn`).
- The React app keeps inputs and results in component state; **API keys are never
  persisted** (no `localStorage`, no query params).

## Milestone 4 — packaging & container readiness

Milestone 4 is **packaging and infrastructure-readiness only** — it changes no
product logic. It adds a Docker image, a `.dockerignore`, and an optional,
**opt-in, local-file-only** JSONL audit export.

> Noxus is a pre-production readiness tester — **not a runtime firewall** and
> **not a compliance certification engine**. No cloud SDKs (BigQuery, Cloud
> Storage, Vertex, etc.) are included; the audit export is plain local NDJSON.

### Build & run the container

The image is a **multi-stage build**: a Node stage builds the React SPA, and the
Python stage installs the backend and bundles the built static files. The final
runtime serves everything from one non-root `uvicorn` process.

```bash
docker build -t noxus-agentsecops:react-local .

# Start the React cockpit + API (default command, default port 8787):
docker run --rm -p 8787:8787 \
  -e NOXUS_API_PORT=8787 \
  noxus-agentsecops:react-local
# open http://localhost:8787
```

Override the port:

```bash
docker run --rm -p 9000:9000 -e NOXUS_API_PORT=9000 noxus-agentsecops:react-local
```

In the **web UI**, Agent-Assisted Mode is configured in-app (provider type, base
URL, API key, models) — no environment variables are needed. The **CLI** path
still reads `NOXUS_LLM_*` env vars and can be run inside the container via a
command override (deterministic mode needs none):

```bash
# Agent-assisted CLI inside the container (env-var provider config):
docker run --rm \
  -e NOXUS_LLM_BASE_URL=http://host.docker.internal:4000/v1 \
  -e NOXUS_LLM_API_KEY=sk-local \
  -e NOXUS_RED_MODEL=gemini-3.5-flash \
  -e NOXUS_JUDGE_MODEL=gemini-3.5-flash \
  -e NOXUS_TUNING_MODEL=gemini-3.1-pro-preview \
  noxus-agentsecops:react-local \
  noxus run --mode agent-assisted \
    --system-prompt src/noxus/samples/system_prompt.txt \
    --policy src/noxus/samples/security_policy.yaml \
    --business-context src/noxus/samples/business_context.md

# Deterministic CLI inside the container (no credentials):
docker run --rm noxus-agentsecops:react-local \
  noxus run --mode deterministic \
    --system-prompt src/noxus/samples/system_prompt.txt \
    --policy src/noxus/samples/security_policy.yaml \
    --business-context src/noxus/samples/business_context.md
```

The final image is based on `python:3.11-slim`, runs as the non-root user
`noxus_user`, sets `PYTHONDONTWRITEBYTECODE=1` / `PYTHONUNBUFFERED=1`, and bundles
the built React SPA under `/app/web_static`. `.dockerignore` keeps `.git/`,
`.venv/`, caches, `node_modules/`, `outputs/`, `reports/`, `tmp/`, `*.log`,
`.env*`, and `tests/` out of the image (while keeping `src/`, `pyproject.toml`,
`README.md`, and the sample files).

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
cloud credentials, or a running web server.

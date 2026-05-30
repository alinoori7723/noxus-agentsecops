# Noxus AgentSecOps — AI Security Readiness Tester for LLM Apps

Noxus AgentSecOps tests whether an LLM application is ready to handle adversarial
input safely. It runs an **attack → evaluate → patch → retest** loop against a
target app's system prompt and security policy, then produces a readiness report.

This repository contains **Milestone 1**: a fully **deterministic, local Python
skeleton**. It proves the entire loop can run end-to-end **without any LLM,
network, or cloud dependency**.

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

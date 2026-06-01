# Noxus AgentSecOps — Google Challenge Application (Draft)

Draft answers for the Google for Startups AI Agents Challenge application. Tone:
precise, confident, no exaggerated claims.

## A. Project name

Noxus AgentSecOps

## B. One-liner

Autonomous red-team and policy tuning for enterprise AI apps.

## C. Problem

Enterprise AI apps can leak sensitive or proprietary context and are vulnerable
to prompt injection delivered through untrusted documents, tickets, and pasted
content. Today, teams check this with ad-hoc manual review. They lack a
repeatable, evidence-producing way to test and tune their system prompts and
security policies *before* shipping to production.

## D. Solution

Noxus generates structured adversarial probes, evaluates failures with evidence,
proposes schema-bound policy/prompt patches, applies those patches through a
deterministic engine, reruns the probes, and produces a before/after readiness
report. The result is an honest verdict (`PASS` / `CONDITIONAL_PASS` /
`HUMAN_REVIEW_REQUIRED` / `FAIL`) plus the evidence behind it.

## E. Why this is an AI agent

It closes the loop with bounded, cooperating agents:

- **Red Team Agent** generates schema-validated probes (must include an indirect
  prompt-injection probe).
- **Semantic Judge** evaluates the cases that need semantic judgment
  (indirect injection, proprietary-context exposure) and *supplements* — never
  replaces — the deterministic findings.
- **Policy Tuning Agent** proposes structured patch operations.
- **Deterministic patch engine** applies only the allowed changes.
- The system **retests**, and the loop is bounded by `MAX_TUNING_ITERATIONS = 2`.

## F. Why this is technically trustworthy

- Every LLM output is validated against **Pydantic v2 schemas**.
- **One** bounded repair attempt; on failure a `SchemaContractError` cleanly maps
  to `HUMAN_REVIEW_REQUIRED` — no dirty continuation with partial state.
- The **deterministic evaluator** is always the baseline; agents only add to it.
- The LLM **cannot directly mutate** YAML or prompts — only the deterministic
  patch engine applies changes.
- An **AST/static scope guard** blocks forbidden cloud/provider SDK imports and
  keeps the web framework (FastAPI) isolated to the API adapter (`api_server.py`).
- **165 automated tests**, including 35 deterministic regression tests, plus a
  Vitest frontend suite.

## G. Google ecosystem fit

- **Gemini-compatible model routing** through a LiteLLM-compatible interface
  (model names are configurable strings, no provider lock-in).
- **Gemini Flash-class** models for fast probe generation and judging;
  **Gemini Pro-class** models for deeper policy-tuning reasoning.
- The **JSONL audit export is cloud-agnostic** newline-delimited JSON that can be
  ingested by external pipelines — including BigQuery — **without embedding any
  cloud SDK** in the product.
- It **complements** Google security products (e.g. Model Armor, Sensitive Data
  Protection) by testing and tuning readiness; it does not replace them.

## H. Business case

**Target users:** AI product teams, security teams, platform teams, and
enterprises deploying internal copilots.

**Value:**

- Reduces the risk of an unsafe launch.
- Produces an evidence report for security/product review.
- Turns prompt/policy security from ad-hoc review into a repeatable test-and-tune
  workflow.

## I. Current MVP

All four engineering milestones are complete and accepted:

1. Deterministic readiness skeleton.
2. Schema-bound agent layer.
3. Local demo UI with truthful report presentation.
4. Container packaging and local JSONL audit export.

## J. Limitations / honesty

- **Not** a runtime firewall.
- **Not** a compliance certification engine.
- **No** production traffic interception.
- Proprietary-context exposure **intentionally remains an open risk** in the
  current demo (no approved auto-remediation), so the demo ends at
  `CONDITIONAL_PASS` rather than a fabricated `PASS`.

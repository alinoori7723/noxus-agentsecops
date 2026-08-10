# Noxus AgentSecOps — Positioning Guardrails

This file exists to prevent messaging drift. When in doubt about how to describe
Noxus anywhere (README, pitch, demo, application), follow this.

## Product name

Noxus AgentSecOps

## Tagline

Bounded agentic audit and remediation-readiness loop for enterprise AI apps.

## Canonical positioning (use verbatim)

Noxus is a bounded agentic audit and remediation-readiness loop. It proposes
schema-bound remediations, applies only deterministic allowed patches, measures
which findings were resolved, and refuses to mark the target safe when
unsupported risks remain.

## What it is

- A **pre-production AI security readiness tester** for LLM apps.
- A **bounded agentic audit and remediation-readiness loop** (generate probes →
  evaluate → propose schema-bound patches → apply only deterministic allowed
  patches → retest → measure resolved vs unresolved), bounded by
  `MAX_TUNING_ITERATIONS = 2`. It does **not** fully autonomously remediate.
- A **structured readiness tester** for system prompts and security policies.
- An **evidence-backed report generator** for security/product review.
- A **bounded agentic workflow with deterministic safety rails** — the LLM
  proposes schema-bound objects; a deterministic engine applies changes.

## What it is NOT

- Not a runtime firewall.
- Not a DLP replacement.
- Not a compliance certification engine.
- Not a production traffic gateway.
- Not a replacement for Google security products (Model Armor, Sensitive Data
  Protection, etc.).

## Primary audience

AI product teams, security teams, platform teams, and enterprises deploying
internal copilots.

## Differentiation

- **Deterministic core + schema-bound agents:** reproducible baseline, with
  LLM agents that can only emit validated objects.
- **Agents propose, deterministic engine applies:** the LLM never directly edits
  prompts or YAML.
- **Honest verdicts:** `CONDITIONAL_PASS` and visible open risks instead of a
  fabricated `PASS`; `HUMAN_REVIEW_REQUIRED` when a schema contract fails.
- **Evidence-first:** every finding carries evidence and an honest detection
  label.

## Google ecosystem alignment

- Gemini-compatible model routing via a LiteLLM-compatible interface (configurable
  model names; Flash-class for fast probe/judge, Pro-class for policy reasoning).
- Cloud-agnostic local JSONL audit output that external pipelines (including
  BigQuery) can ingest — without embedding cloud SDKs.
- Complements, rather than replaces, Google security products.

## Words / claims to AVOID

- "certifies compliance"
- "prevents all prompt injection"
- "replaces Model Armor"
- "replaces Sensitive Data Protection"
- "runtime firewall"
- "production gateway"
- "guaranteed safe"
- "fully compliant"

## Preferred wording

- "readiness tester"
- "pre-production security validation"
- "evidence-backed report"
- "bounded agentic loop"
- "structured policy tuning"
- "human-review required when uncertain"

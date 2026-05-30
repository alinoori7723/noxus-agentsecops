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

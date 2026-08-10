# Architecture

Noxus separates untrusted inputs and optional model output from the code allowed
to mutate a target configuration. The same core assessment flow serves the CLI
and HTTP API.

## Assessment flow

1. `policy_loader.py` loads the system prompt, YAML policy, and supporting
   business context.
2. `probe_registry.py` supplies the deterministic regression probes.
3. `target_simulator.py` executes the bundled deterministic target and
   `evaluator.py` records evidence-backed findings.
4. In agent-assisted mode, `agents.py` requests schema-bound probe, judgment,
   and tuning objects through the provider interface. Deterministic probes remain
   in the run.
5. `patch_mapper.py` or the Policy Tuning Agent proposes structured operations.
   `patch_engine.py` validates and applies only its supported operations.
6. `orchestrator.py` retests the patched configuration, compares before and after
   evidence, and delegates report construction to `report.py` and
   `remediation.py`.
7. The CLI, `api_core.py`, and `ui_formatters.py` render the same structured
   result. `audit_export.py` can append it to a caller-selected local JSONL file.

## Interfaces

- `noxus run` provides deterministic and agent-assisted CLI modes.
- `api_server.py` is the only production module that imports FastAPI. It exposes
  health, sample-input, proof, provider-test, assessment, and local audit-export
  endpoints.
- `apps/web/` is a React/TypeScript single-page application. Vite serves it in
  development; FastAPI serves the built assets for a single-origin local run.
- The Dockerfile builds the frontend with Node 20 and runs the Python 3.11 image
  as the non-root `noxus_user` account.

## State and data handling

Assessment inputs and results remain in process or browser component state unless
the user explicitly requests local JSONL export. The backend confines web static
files to the configured build directory and audit filenames to the configured
audit directory. Provider credentials are request-scoped and are not included in
the structured report.

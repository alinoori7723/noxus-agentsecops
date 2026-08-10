# Noxus AgentSecOps

Noxus is a fail-closed, pre-production security readiness testbed for LLM
applications. It evaluates system prompts and YAML security policies, applies
only allowlisted deterministic remediations, retests the target, and produces an
evidence-backed readiness report.

## Problem

LLM applications often process untrusted documents, tickets, and user input
alongside sensitive business context. Ad hoc prompt review does not provide a
repeatable way to exercise those trust boundaries, trace findings to evidence,
or verify that a proposed policy change resolves the original failure. Noxus
provides a bounded test-and-retest workflow for that pre-production work.

## Implemented capabilities

- Deterministic probes for indirect prompt injection, PII leakage, fake-secret
  exfiltration, customer-identifier leakage, and proprietary-context exposure.
- An optional bounded agentic audit and remediation-readiness loop with
  schema-bound Red Team, Semantic Judge, and Policy Tuning roles.
- Strict Pydantic contracts with one bounded repair attempt for malformed model
  output; unrecoverable contract failures route to `HUMAN_REVIEW_REQUIRED`.
- A deterministic patch engine that is the only component allowed to change a
  prompt or policy, followed by a retest against the same baseline.
- A Python CLI, FastAPI application, React/TypeScript cockpit, and opt-in local
  JSONL audit export.
- Multi-stage Docker packaging with a non-root runtime user.

## Architecture

| Layer | Responsibility |
| --- | --- |
| CLI and React cockpit | Collect inputs and present evidence, remediation lineage, and open risks. |
| FastAPI adapter | Expose `/api/health`, `/api/proof`, `/api/sample-inputs`, and `/api/assessments/run`. |
| Orchestrator | Run the deterministic baseline and coordinate the optional bounded agent roles. |
| Evaluators and agents | Emit evidence-backed findings and schema-validated proposals. |
| Deterministic patch engine | Apply only supported prompt and policy operations, then trigger the retest. |
| Report and audit export | Preserve before/after results, open risks, and local JSONL evidence. |

See [Architecture](docs/architecture.md) for component and data-flow details.

## Quick start

Prerequisites are Python 3.11 or newer and Node.js 20 for the web application.
Deterministic mode makes no network calls and requires no provider credentials.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

noxus run --mode deterministic \
  --system-prompt src/noxus/samples/system_prompt.txt \
  --policy src/noxus/samples/security_policy.yaml \
  --business-context src/noxus/samples/support_case_base.md
```

To run the built web application:

```bash
cd apps/web
npm ci
npm run typecheck
npm run build
cd ../..

NOXUS_WEB_DIST=apps/web/dist uvicorn noxus.api_server:app --port 8787
```

Open <http://localhost:8787>. The default deterministic assessment needs no API
key. Agent-assisted mode requires a compatible model endpoint and explicit
provider configuration.

## Validation

Python tests:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

Frontend tests, strict TypeScript checking, and production build:

```bash
cd apps/web
npm ci
npm run test
npm run typecheck
npm run build
```

Python package metadata can be validated with:

```bash
.venv/bin/python -m pip wheel --no-deps --wheel-dir /tmp/noxus-wheel .
```

Release verification on 2026-08-11 completed with:

- 526 Python tests passed.
- 63 frontend tests passed.
- Strict TypeScript checking passed.
- The Vite production build passed.

No standalone Python lint or type-check command and no frontend lint command are
currently configured.

## Security model

- The deterministic baseline is local, reproducible, and credential-free.
- Model output cannot directly edit target inputs; agents can only propose
  schema-bound operations and the deterministic engine enforces the allowlist.
- Agent execution is bounded by `MAX_TUNING_ITERATIONS = 2`.
- Schema failures, timeouts, and unsupported remediation paths preserve the
  available baseline evidence and surface human-review requirements instead of
  manufacturing a successful result.
- API keys supplied to agent-assisted assessments are used in memory for the
  request and are excluded from reports, audit exports, URLs, and browser
  persistence.
- Proprietary-context exposure has no approved automatic remediation and remains
  an explicit open risk in the bundled scenario.

See [Security model](docs/security-model.md) for trust boundaries and failure
behavior.

## Current limitations and non-claims

Noxus is not a runtime firewall, production traffic gateway, DLP replacement,
or compliance certification engine. It does not automatically secure an
application or claim to prevent every prompt injection. The bundled target is a
deterministic simulator, and its marker-based checks are a regression testbed,
not a substitute for production telemetry or independent security review.

Agent-assisted mode depends on an externally operated compatible model endpoint.
The audit export is local newline-delimited JSON; Noxus does not include cloud
storage, deployment, or data-warehouse integrations.

The current frontend lockfile reports eight `npm audit` findings in development
tooling (three moderate, four high, and one critical); `npm audit --omit=dev`
reports zero production-dependency findings. Resolving the remaining Vite/Vitest
toolchain findings requires a major-version migration and is outside this
release-focused cleanup.

## Repository structure

```text
apps/web/          React, TypeScript, Vite, and Vitest frontend
docs/              Current architecture and security documentation
docs/archive/      Historical planning, milestone, competition, and draft material
scripts/           Local release validation and live smoke helpers
src/noxus/         Python package, API, orchestration, evaluation, and reporting
tests/             Python unit, integration, security, and release-hygiene tests
Dockerfile         Multi-stage web build and non-root Python runtime image
pyproject.toml     Python package and pytest configuration
```

## Documentation

- [Architecture](docs/architecture.md)
- [Security model](docs/security-model.md)
- [Historical material](docs/archive/README.md)
- [Legacy tag inventory](docs/archive/legacy-tags.md)

## Contributing

Open an issue describing the proposed change and its security or compatibility
impact before substantial work. Keep changes focused, add or update tests for
observable behavior, and run the Python and frontend validation commands above.
Do not include real credentials in fixtures, logs, reports, or examples.

## License

Licensed under the [Apache License 2.0](LICENSE) (`Apache-2.0`).

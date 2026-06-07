# Noxus AgentSecOps — Submission Checklist

Run through this before submitting. Everything here is local; no cloud
credentials, no network sink.

## Git tags

- [ ] `milestone-1-complete`
- [ ] `milestone-2-complete`
- [ ] `milestone-3-complete`
- [ ] `milestone-4-complete`

```bash
git tag --list
```

## Tests

- [ ] Full suite green (release verification: **526 Python tests** with dev extras installed).
- [ ] Frontend tests green (**63 frontend tests**).

### Canonical release validation

Canonical release validation uses a clean virtual environment with
`pip install -e '.[dev]'`. The dev extras (e.g. httpx for the FastAPI test
client) are required for the full suite, so this clean-venv count is the
authoritative release count. Host `pytest` is a quick local check only — when
optional dev extras are missing it reports **fewer** tests, so the host count is
not the canonical release count.

The whole flow is scripted in `scripts/final_release_validate.sh` (clean venv +
dev extras → pytest → frontend `npm ci`/build/test → docker build → `/api/health`
and `/api/proof` smoke → traversal 404 checks). It needs no provider credentials,
writes no secrets, and removes its temporary venv/node_modules/dist on exit.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q          # release-verified at 526 Python tests (httpx from dev extras)
cd apps/web && npm ci && npm run test && cd -
# or, end-to-end:
bash scripts/final_release_validate.sh
```

### Safe Docker smoke port

The smoke step uses a dedicated, named smoke container (`noxus-edge-smoke`) and
never stops an unknown/existing demo container. It prefers the default demo port
**8787**; when 8787 is already busy it falls back to the alternate smoke port
**8877** and reports that instead of stopping whatever is already running.

### Legacy score field presentation aliases (technical debt note)

`before_score` and `after_score` are **legacy internal numeric readiness fields**
(0–100, higher is safer). They are kept for API/computation stability and must
NOT be renamed.

The canonical user-facing labels are `Baseline readiness score` and
`Readiness gate score` (surfaced via the additive presentation aliases
`baseline_readiness_score_label` / `readiness_gate_score_label`). Do not label
these higher-is-better scores as a "risk score" in any future UI/API
presentation; remaining risk is shown qualitatively (`qualitative_risk_level`)
and via failed probes / unresolved findings / human-review requirements.

## Docker

- [ ] Image builds (multi-stage: Node builds the SPA, Python serves it).
- [ ] Container starts the React cockpit + FastAPI API on port 8787.
- [ ] Runs as non-root (`noxus_user`).
- [ ] `GET /api/health` returns ok; `/` serves the SPA.

```bash
docker build -t noxus-agentsecops:react-local .
docker run --rm -p 8787:8787 noxus-agentsecops:react-local
# open http://localhost:8787
```

## CLI

- [ ] Deterministic CLI exits 0.
- [ ] Output shows `[DETERMINISTIC SIMULATION]`.
- [ ] Final readiness is `CONDITIONAL_PASS`.

```bash
PYTHONPATH=src python3 -m noxus.cli run --mode deterministic --system-prompt src/noxus/samples/system_prompt.txt --policy src/noxus/samples/security_policy.yaml --business-context src/noxus/samples/business_context.md
```

## UI

- [ ] React cockpit loads (dev `http://localhost:5173`, or built/container
      `http://localhost:8787`).
- [ ] Deterministic Mode works without credentials.
- [ ] Agent-Assisted provider panel works (password API-key field, Gemini presets).
- [ ] Edits to prompt/policy/context persist in the session.
- [ ] Open risks and honest labels are visible.
- [ ] Traversal blocked: `curl --path-as-is http://localhost:8787/../pyproject.toml`
      returns 404.

## Audit export

- [ ] Opt-in flag writes exactly one JSON line per run.
- [ ] No file is written without the flag.

```bash
mkdir -p outputs/audit
PYTHONPATH=src python3 -m noxus.cli run --mode deterministic --system-prompt src/noxus/samples/system_prompt.txt --policy src/noxus/samples/security_policy.yaml --business-context src/noxus/samples/business_context.md --audit-jsonl-output outputs/audit/readiness_reports.jsonl
```

## Demo recording

- [ ] ≤ 3 minutes, following `docs/demo-script.md`.
- [ ] Shows failure-first, then patch, then `CONDITIONAL_PASS`.
- [ ] Shows `[DETERMINISTIC SIMULATION]` label.
- [ ] Shows proprietary-context exposure remaining as an open risk.
- [ ] Does **not** show a fake fully-safe result.

### Screenshot / screen-recording checklist

- [ ] React cockpit header (readiness-tester, not-a-firewall note).
- [ ] Target Configuration panel (weak policy visible).
- [ ] Red/Blue dashboard — red side (failing probes + evidence).
- [ ] `[DETERMINISTIC SIMULATION]` label close-up.
- [ ] Blue side — patch operations + real `[CRITICAL_SAFETY_RAILS]` preview.
- [ ] Iteration timeline (before → after score movement).
- [ ] Final amber `CONDITIONAL_PASS` badge + open risks list.

## Challenge answers

- [ ] `docs/challenge-application-draft.md` reviewed and finalized.
- [ ] Positioning matches `docs/positioning.md` (no forbidden claims).

## Known limitations

- [ ] Limitations stated honestly (see README + `docs/positioning.md`):
  not a runtime firewall, not compliance certification, no production traffic
  interception, no real cloud SDK, proprietary-context exposure intentionally
  remains an open risk.

## Deferred after challenge MVP

These are intentional, documented deferrals — not gaps to hide. The MVP
deliberately prefers a fail-safe `HUMAN_REVIEW_REQUIRED` over over-coercing
malformed LLM output:

- **Per-probe Semantic Judge partial retention.** When the judge breaks its
  schema contract the run drops the whole semantic supplement (keeping the
  deterministic + valid red-team evidence) rather than retaining a subset of
  per-probe judgments. Deferred to avoid half-state reports before a clearer
  evidence-ledger design exists.
- **Multi-attempt tuning self-correction (beyond the single bounded repair).**
  A non-conforming patch vocabulary fails safe to `HUMAN_REVIEW_REQUIRED`.
  Deferred because auto-coercing unknown patch fields risks inventing unsafe
  target/path semantics — the deterministic patch engine must stay the only
  applier, on an explicit allowlist.
- **Dynamic CI-derived test-count publication.** The proof/docs counts are a
  declared release-verification figure (`NOXUS_TEST_COUNT`), updated as a
  metadata step — not a runtime/dynamic count.

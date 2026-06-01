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

- [ ] Full suite green (expected: **165 passed** with dev extras installed).
- [ ] Frontend tests green (15 Vitest tests).

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q          # 165 passed (httpx from dev extras)
cd apps/web && npm ci && npm run test && cd -
```

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

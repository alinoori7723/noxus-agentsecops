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

- [ ] Full suite green (expected: **89 passed**).

```bash
PYTHONPATH=src python3 -m pytest -q
```

## Docker

- [ ] Image builds.
- [ ] Container starts the Streamlit UI on the expected port.
- [ ] Runs as non-root (`noxus_user`).

```bash
docker build -t noxus-agentsecops:local .
docker run --rm -p 8501:8501 noxus-agentsecops:local
```

## CLI

- [ ] Deterministic CLI exits 0.
- [ ] Output shows `[DETERMINISTIC SIMULATION]`.
- [ ] Final readiness is `CONDITIONAL_PASS`.

```bash
PYTHONPATH=src python3 -m noxus.cli run --mode deterministic --system-prompt src/noxus/samples/system_prompt.txt --policy src/noxus/samples/security_policy.yaml --business-context src/noxus/samples/business_context.md
```

## UI

- [ ] `streamlit run src/noxus/ui_streamlit.py` (or container) loads.
- [ ] Deterministic Mode works without credentials.
- [ ] Edits to prompt/policy/context persist across reruns.
- [ ] Open risks and honest labels are visible.

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

- [ ] Streamlit header (readiness-tester, not-a-firewall note).
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

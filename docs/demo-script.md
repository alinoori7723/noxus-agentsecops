# Noxus AgentSecOps — 3 Minute Demo Script

A tight script for a live demo or screen recording. Total ≈ 3 minutes. Keep the
honest framing: this is **pre-production readiness testing, not a runtime
firewall**, and the demo intentionally starts by failing and ends at
`CONDITIONAL_PASS` with a visible open risk.

---

## 1. Opening (≈15s)

> "This is Noxus AgentSecOps — an autonomous red-team and policy-tuning loop that
> tests whether an enterprise LLM app is *ready* for production. It's a
> pre-production security readiness tester — **not** a runtime firewall and
> **not** a compliance certification engine."

Show the React cockpit header (`Pre-production readiness tester, not a runtime firewall`) at http://localhost:8787.

## 2. Target app setup (≈20s)

Open the **Target Configuration** panel and show the three inputs:

- `system_prompt.txt` — a normal support-bot business prompt.
- `security_policy.yaml` — **intentionally weak** (empty masks, indirect
  injection detection off, no human-review categories).
- `business_context.md` — documentation-only context.

> "We're testing a deliberately weak configuration so you can see the loop work."

## 3. Red Team phase (≈35s)

Click **Run Readiness Assessment** (Deterministic Mode). Show the probes on the
red side of the dashboard.

> "Noxus runs structured probes — indirect prompt injection, PII leakage, fake
> secret exfiltration, customer-identifier leakage, proprietary-context exposure.
> In deterministic mode these are a fixed regression baseline. In agent-assisted
> mode a Red Team Agent generates schema-validated probes on top of that
> baseline — and it's *required* to include an indirect-injection probe."

## 4. Failure-first evidence (≈30s)

Show the **Before** column / first-run failures.

> "It fails first — on purpose. Each failure is evidence-backed. Notice the
> indirect prompt-injection finding is honestly labeled `[DETERMINISTIC
> SIMULATION]` — we never overstate what the detector is doing."

Point at the `[DETERMINISTIC SIMULATION]` label and the evidence snippets.

## 5. Blue Team patching (≈40s)

Show the blue side of the dashboard: the `PatchOperations` and the
`[CRITICAL_SAFETY_RAILS]` preview.

> "Now the blue side. A Policy Tuning Agent proposes **schema-bound** patch
> operations — but the LLM never edits the prompt or YAML directly. A
> deterministic patch engine applies the allowed changes. Here's the real
> `[CRITICAL_SAFETY_RAILS]` block it inserted — that preview is rendered from
> actual execution telemetry, not a hardcoded string."

Emphasize: agents *propose*, deterministic engine *applies*.

## 6. Retest and result (≈35s)

Show the **After** column, the score movement, and the final badge.

> "After patching, Noxus reruns the same probes. The indirect-injection case now
> passes, the score improves — and the final verdict is `CONDITIONAL_PASS`,
> shown in amber. Proprietary-context exposure stays an **open risk** because
> there's no approved auto-fix for it. An honest conditional result beats a fake
> green light."

Point at the open-risk line for `proprietary_context_exposure`.

## 7. Engineering proof (≈25s)

> "Under the hood: release verification of 351 Python tests (plus 36 frontend tests), including 35 deterministic regression tests,
> plus a Vitest frontend suite. Every LLM output is validated against Pydantic
> schemas with one bounded repair attempt — failure routes to
> `HUMAN_REVIEW_REQUIRED`. The loop is bounded at `MAX_TUNING_ITERATIONS = 2`. An
> AST static scope guard blocks forbidden cloud SDKs and keeps the web framework
> isolated to the API adapter. And there's an opt-in, local-only JSONL audit
> export."

## 8. Closing (≈20s)

> "For enterprise AI teams, this turns prompt-and-policy security from ad-hoc
> review into a repeatable test-and-tune workflow with an evidence report. It
> routes to Gemini-class models through a LiteLLM-compatible interface and its
> audit output is cloud-agnostic — it complements Google's security products
> rather than replacing them."

---

**Do not** show a fully-safe result, and **do not** hide the open risk. The honest
`CONDITIONAL_PASS` is the point.

# Security model

Noxus is designed as a pre-production testbed with explicit trust boundaries. It
does not sit in a production request path and does not claim to make a target
safe.

## Trust boundaries

- Target prompts, policies, support cases, documents, and model responses are
  untrusted assessment input.
- The deterministic probe registry and evaluator form the reproducible baseline.
- Optional LLM roles emit strict Pydantic objects. They cannot directly write a
  prompt, policy, report, or audit file.
- The deterministic patch engine is the only prompt/policy mutation boundary and
  accepts a fixed operation vocabulary and policy-path allowlist.
- Audit export is opt-in and local. The HTTP adapter accepts only a sanitized
  JSONL filename under the configured audit directory.

## Fail-closed behavior

Model output receives at most one bounded schema-repair attempt. An unrecoverable
contract failure stops the affected path, preserves already collected
deterministic evidence, applies no unsupported patch, and records
`HUMAN_REVIEW_REQUIRED`. Timeouts and provider failures use similarly explicit
diagnostics without including API keys.

The retest does not erase unresolved baseline risk. In the bundled scenario,
proprietary-context exposure has no approved automatic remediation, so it remains
visible and prevents a full `PASS`.

## Credential handling

Deterministic mode uses no provider credentials and makes no model call. In
agent-assisted web requests, an API key is used in memory to construct the
provider and is excluded from logs, URLs, reports, audit exports, response data,
and browser persistence. Operators remain responsible for the security and data
handling of any configured external model endpoint.

## Non-claims

Noxus is not a runtime firewall, a DLP system, a compliance certification tool,
or a production gateway. Its deterministic target and marker-based detections are
controlled regression fixtures. Results require human interpretation and do not
replace deployment-specific threat modeling, penetration testing, monitoring, or
incident response.

# Threat model

## Assets and actors

Assets include provider credentials, target prompts and business context,
assessment integrity, local audit files, and the host filesystem. Relevant
actors are an operator, an untrusted target-document author, a malicious or
malfunctioning model endpoint, and a caller able to reach the local API.

## Boundaries and residual risks

| Threat | Enforced control | Remaining responsibility |
| --- | --- | --- |
| Instructions hidden in target context | Separate deterministic baseline, schema validation, fixed patch vocabulary | Simulator coverage cannot establish resistance of a real deployed model |
| Malformed or overreaching agent output | Strict models, one repair attempt, allowlisted mutation, human-review fallback | Model judgments can be wrong even when schema-valid |
| Secret disclosure from the browser | Server profiles by default; manual credentials require local opt-in | Protect server environment, local processes, and browser extensions |
| Client-selected provider egress | Server-owned endpoint/model selection; mixed profile and manual config rejected | Secure configured gateways and restrict host egress |
| Malicious provider endpoint | HTTPS for remote profiles, bounded requests, schema validation | The provider receives assessment content; choose and govern it accordingly |
| Request-validation leakage | Generic validation errors omit submitted values | Input and output reports may themselves contain sensitive target data |
| Arbitrary file write or static traversal | Confined audit names and static roots; unknown routes return 404 | Protect audit directory permissions and disk capacity |
| Dependency or build compromise | Lockfiles, frozen/hashed installs, pinned Actions, audits and image scans | Review dependency updates and upstream advisories |
| Unauthorized assessment / resource exhaustion | Loopback default and bounded agent workflow | API has no auth or rate limiting; isolate access and add external controls |

## Exclusions

Noxus does not provide tenant isolation, runtime traffic enforcement, arbitrary
code sandboxing, production DLP, or compliance certification. Report results
are evidence from configured probes, not a universal safety score.

An attacker with host or container-runtime access can read process credentials
and alter evidence. Do not run untrusted code alongside sensitive assessments.
Only use synthetic data for public demonstrations and vulnerability reports.

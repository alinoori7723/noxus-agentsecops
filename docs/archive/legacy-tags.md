# Legacy tag inventory

Before the initial public release, the repository used 14 lightweight tags as
internal milestone, demo, submission, and reporting checkpoints. None had an
associated GitHub Release. The table records each direct commit target before
tag consolidation; commit history remains reachable from `main`, and a verified
all-refs Git bundle was created before any deletion.

| Tag | Commit | Commit date | Apparent purpose |
| --- | --- | --- | --- |
| `milestone-1-complete` | `5a84e14d89eb227b7d8922d86a06ed0e1d374ad8` | 2026-05-31 | Deterministic readiness skeleton checkpoint. |
| `milestone-2-complete` | `f3544a3f404f101447f78260281a278f334a90ef` | 2026-05-31 | Schema-bound agent layer checkpoint. |
| `milestone-3-complete` | `b24170ad615861c2371e57a29ccd7de80e939a2d` | 2026-05-31 | Telemetry and UI placeholder-removal checkpoint. |
| `milestone-4-complete` | `2674c76314ba188362cc39d3a4e76babffac2db9` | 2026-05-31 | Container packaging and local JSONL export checkpoint. |
| `submission-packaging` | `a67edeac9ee28a61c25b4c711e489989e7ed2694` | 2026-05-31 | Judge quick-start and challenge packaging checkpoint. |
| `react-ui-replacement` | `194aa848521c7826f41595452719026c2e270019` | 2026-06-01 | React API replacement hardening checkpoint. |
| `react-cockpit-final` | `70c3bfb46795af5193fb445d5dd1d7616cd19bcf` | 2026-06-03 | React cockpit and provider-observability checkpoint. |
| `agent-runtime-hardened-final` | `0a96ea88e222819ef8567d36343d7f5201781566` | 2026-06-04 | LLM runtime hardening checkpoint. |
| `demo-ready-final` | `87515ed9e6d76f43376ed3e1ca79bb06d982278a` | 2026-06-04 | Demo-readiness checkpoint. |
| `google-submission-final` | `314f5f09d813959b5b04557d2cea4282c9d6c4bb` | 2026-06-04 | Competition submission and positioning checkpoint. |
| `google-demo-ux-final` | `91c2018cbc26c75cab24e54d843f794b0f96170a` | 2026-06-05 | Demo scoring and remediation UX checkpoint. |
| `google-live-demo-final` | `4e8d82beb259ac5079b7b73cc4cc427e03d2be07` | 2026-06-06 | Live-provider timeout-resilience checkpoint. |
| `google-kpi-lineage-final` | `07f5d34527b59d2e7535ab90636078194471bcc2` | 2026-06-07 | Readiness scoring and patch-lineage checkpoint. |
| `google-final-reporting` | `753ed3f2a675d550d250ca201ef603beadd7b013` | 2026-06-07 | Audit reporting consistency checkpoint. |

The four milestone tags were referenced only by the archived submission
checklist. No repository issue, pull request, GitHub Release, publication
identifier, or tracked external-publication metadata referenced any legacy tag
at the time of consolidation.

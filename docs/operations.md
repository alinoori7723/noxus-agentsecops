# Operations

## Runtime

Use Python 3.11 or newer and Node.js 24.15+ within Node 24. CI covers Python
3.11 and 3.13. The committed `uv.lock` and npm lockfile pin the resolved trees;
`uv sync --frozen` and `npm ci` reject dependency drift. CI uses uv 0.10.9.

The native API defaults to `127.0.0.1:8787`. `NOXUS_API_PORT` changes the port;
`NOXUS_WEB_DIST` selects a built frontend directory. Container processes bind
internally to `0.0.0.0`; publish only on loopback:

```bash
docker build -t noxus:local .
docker run --rm --read-only --tmpfs /tmp --cap-drop=ALL \
  --security-opt=no-new-privileges -p 127.0.0.1:8787:8787 noxus:local
```

The API has no authentication or TLS. Do not expose it directly to the internet.
Use access control, TLS termination, rate limits, and an egress policy before
considering a private shared deployment. Noxus is local / pre-production software.

## Server provider profiles

Inject the credential into the server environment from your shell or secret
manager. Never commit the value. Configure profiles as JSON in
`NOXUS_PROVIDER_PROFILES`; `api_key_env` names an existing environment variable.
The following profile uses illustrative model IDs; replace them with models
available to your provider account.

```bash
export NOXUS_PROVIDER_PROFILES='{"gemini-prod":{"provider_type":"gemini_native","api_key_env":"GEMINI_API_KEY","red_model":"your-red-model","judge_model":"your-judge-model","tuning_model":"your-tuning-model"}}'
uv run --frozen noxus-api
```

PowerShell equivalent, with `GEMINI_API_KEY` already injected into the process:

```powershell
$env:NOXUS_PROVIDER_PROFILES = '{"gemini-prod":{"provider_type":"gemini_native","api_key_env":"GEMINI_API_KEY","red_model":"your-red-model","judge_model":"your-judge-model","tuning_model":"your-tuning-model"}}'
uv run --frozen noxus-api
```

For a LiteLLM-compatible gateway use `provider_type=openai_compatible` and an
HTTPS `base_url`, or `local_openai_compatible` for a loopback gateway. Remote
HTTP, embedded credentials, URL queries, and URL fragments are rejected.
The profile schema rejects raw `api_key` values and unknown fields.

The cockpit loads names from `GET /api/providers`. Its assessment request is:

```json
{
  "mode": "agent_assisted",
  "provider_profile": "gemini-prod",
  "system_prompt": "Synthetic target prompt",
  "security_policy_yaml": "{}",
  "business_context": "Synthetic case"
}
```

Missing profiles, missing server secrets, and mixed profile/manual requests fail
before any provider call. Diagnostics contact all selected role models and may
incur charges. Only synthetic inputs should be used in public demonstrations. For an optional
live smoke, set `NOXUS_PROVIDER_PROFILE` to a configured name and run
`python scripts/smoke_agent_assisted_live.py`; credentials stay on the server.

Manual credentials are available only when the native server is started with
`NOXUS_ENABLE_MANUAL_KEYS=true` and the peer is a loopback address. This mode is
for local development. Do not enable it behind a proxy or in a shared deployment;
a local proxy can make external requests appear to have a loopback peer.

## Timeouts and audit files

`NOXUS_LLM_TIMEOUT_SECONDS` defaults to 180 seconds, with per-role overrides
`NOXUS_RED_TIMEOUT_SECONDS`, `NOXUS_JUDGE_TIMEOUT_SECONDS`, and
`NOXUS_TUNING_TIMEOUT_SECONDS` (tuning defaults to 240).
`NOXUS_PROVIDER_TEST_TIMEOUT_SECONDS` defaults to 60. Transient agent calls allow
at most two retries by default; provider diagnostics do not retry. Schema repair
is bounded independently. Tuning is capped at two iterations.

Audit export is opt-in. Set `NOXUS_AUDIT_DIR` to a protected writable directory.
Reports may contain sensitive target material: treat them as data, not telemetry
suitable for unrestricted logging. Containers need a writable volume for audit
export; deterministic read-only smoke runs need no volume.

## Validation

Install the locked development environment:

```bash
uv sync --frozen --extra dev
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev ruff format --check .
uv run --frozen --extra dev mypy
uv run --frozen --extra dev pytest --cov=noxus --cov-report=term --cov-report=xml
uv run --frozen --extra dev python -m build --wheel --no-isolation
npm ci --prefix apps/web
npm run lint --prefix apps/web
npm test --prefix apps/web
npm run test:coverage --prefix apps/web
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
npm audit --prefix apps/web
npm audit --prefix apps/web --omit=dev
```

Python coverage measures all package modules, including branches. Frontend
coverage includes application, client, and component code, excluding only test
fixtures, type-only contracts, and the rendering entrypoint. Floors are committed
in `pyproject.toml` and `apps/web/vite.config.ts` after measuring the suites:
88.7% Python branch-inclusive coverage; frontend statements 76.9%, branches
73.7%, functions 70%, and lines 78.8%.
The initial pre-hardening measurements were 86.95% Python branch-inclusive
coverage and 40.18% frontend statement coverage; neither was inferred from test
counts. JUnit and coverage files are retained by CI.

Audit the complete hashed Python dependency set, including development tools:

```bash
mkdir -p reports
uv export --frozen --extra dev --no-emit-project --format requirements-txt --output-file reports/python-audit-requirements.txt
uv run --frozen --extra dev pip-audit --require-hashes --disable-pip -r reports/python-audit-requirements.txt
```

Both npm audits and pip-audit fail on any reported vulnerability. Gitleaks scans
the current branch history and redacts findings. The independent archived branch
is outside the release lineage. Trivy scans the filesystem and final image;
full reports include all severities and unfixed findings. The gate fails on any
HIGH/CRITICAL vulnerability, including those without a published fix and any HIGH/CRITICAL configuration failure.
Lower-severity upstream findings remain visible in the reports and require
operator review; a passing gate does not mean an image has zero advisories.

Linux container validation uses a uniquely named container, an ephemeral
loopback port, non-root/read-only execution, and cleanup of only that container:

```bash
docker build -t noxus:check .
python3 scripts/container_smoke.py noxus:check
```

The smoke verifies the SPA, health, a real deterministic assessment, preservation
of open risks, traversal rejection, and default manual-key rejection. No external
model credential is needed. For a complete Linux check, run
`bash scripts/final_release_validate.sh` with uv, Node 24, and Docker installed.

## Releases

Release only a commit whose CI and Security workflows both pass. Use their JUnit
results for test counts and attach their coverage/audit artifacts. Confirm the
tag points to that exact commit. Do not infer live provider success from mock
transport tests or reuse test counts from an older release.

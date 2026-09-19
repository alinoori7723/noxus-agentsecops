# Security model

Noxus is a pre-production testbed with explicit trust boundaries. It is not a
runtime firewall and does not establish that an application is safe to deploy.

## Untrusted inputs and model output

Target prompts, YAML policies, business context, and provider responses are
untrusted. Policies are parsed with safe YAML loading and strict schemas.
Agents emit structured proposals; only the deterministic patch engine can
mutate a prompt or policy. Unsupported operations cannot become successful fixes.

Model output receives at most one schema-repair attempt. Unrecoverable contracts
route to `HUMAN_REVIEW_REQUIRED`. Role timeouts and provider failures preserve
available baseline evidence and explicit diagnostics. A retest cannot erase an
unresolved baseline finding. The bundled proprietary-context case has no
approved automatic remediation and remains an open risk.

## Credentials

The default web contract accepts a server profile name. The operator injects
credentials through environment variables or a secret store that populates them;
Noxus does not implement a secret-store SDK. Profiles contain environment
variable names, not raw keys. Their endpoints require HTTPS except on loopback.

The profile catalog reveals only names and provider types. Request validation
errors omit submitted values. API request logging records bounded metadata and
never the provider configuration. Keys are excluded from report construction,
audit exports, and browser persistence.

Manual keys require `NOXUS_ENABLE_MANUAL_KEYS=true` and a loopback connection.
They are held in component/request memory and cleared from the form when the
user changes credential mode. This is a local development escape hatch, not a
network deployment setting. Gemini credentials are sent in a header, not a URL.

## HTTP and filesystem boundaries

The native API binds to `127.0.0.1` by default. CORS is disabled unless explicitly
configured for local development. The API does not supply authentication,
authorization, TLS, rate limits, tenant isolation, or an application firewall.
Do not expose it directly to the internet. A private deployment requires those
controls outside Noxus and a review of provider egress and submitted data.

Audit export is opt-in and local, confined to a server-configured directory.
The caller may select a sanitized filename, never a path. Static assets are
restricted to the built web root. Container application files are root-owned;
only the audit output directory is writable by the runtime user.

## Evidence limits

Deterministic markers are regression fixtures. Mock provider tests establish
transport and contract behavior; they do not prove live model quality. Live
provider diagnostics make external calls and can incur charges. Dependency
scans reflect the advisory databases at scan time. See the
[threat model](threat-model.md) and [validation policy](operations.md#validation).

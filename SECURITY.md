# Security policy

## Supported versions

Security fixes target the latest published release and the `main` branch.
Earlier releases and archival branches are unsupported; upgrade to the latest
release before reporting a dependency issue. Noxus is a local / pre-production
testbed and is not supported as an internet-facing service.

## Report privately

Use [GitHub private vulnerability reporting](https://github.com/alinoori7723/noxus-agentsecops/security/advisories/new).
Private vulnerability reporting is enabled for this repository. Do not open a
public issue for an unpatched vulnerability.

Include the affected version or commit, environment, minimal reproduction,
expected versus actual behavior, and the trust boundary or data at risk. Use
synthetic data and placeholders for credentials. Sanitized logs and proposed
fixes are welcome.

Never post real API keys, authorization headers, private prompts, customer data,
complete unredacted reports, or working exploits against third-party systems in
public issues, pull requests, or attachments. If a credential was exposed,
revoke it with its provider; deleting a message does not revoke the credential.

The maintainer will acknowledge and triage reports as capacity permits, agree
on remediation and coordinated disclosure privately, and publish an advisory
when appropriate. No response-time SLA or bounty program is offered.

See the [threat model](docs/threat-model.md) for intended boundaries and the
[operations guide](docs/operations.md) for deployment constraints.

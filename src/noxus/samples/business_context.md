# Acme Cloud — Business Context (Documentation Only)

Acme Cloud is a B2B SaaS platform. SupportBot assists human support agents by
summarizing customer tickets, emails, and attached documents.

> NOTE (Milestone 1): This business context is loaded into the readiness report
> metadata for documentation purposes only. It MUST NOT drive any deterministic
> security decision in Milestone 1.

Typical sensitive data in this domain:
- Customer identifiers (e.g. CUST-#######) and internal ticket IDs.
- Contact PII such as emails and phone numbers.
- Service credentials / API keys (must never be exposed).
- Confidential roadmap and proprietary internal pricing notes.

# Security Policy

## Supported versions

| Component | Supported |
|---|---|
| ezop-platform (latest) | ✅ |
| ezop-light-ui (latest) | ✅ |
| ezop-sdk/python (latest) | ✅ |
| Older releases | ❌ |

Only the latest release of each component receives security fixes.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities by emailing **security@ezop.ai**. Include:

- A description of the vulnerability and its potential impact
- The affected component (`ezop-platform`, `ezop-light-ui`, or `ezop-sdk`)
- Steps to reproduce or a proof-of-concept
- Your name/handle if you'd like to be credited

We'll do our best to respond and address issues as time allows. This is an open-source project maintained on a volunteer basis — there are no guaranteed response times.

## Scope

Areas of particular interest:

- **Authentication** — API key handling in `ezop-platform`, NextAuth session management in `ezop-light-ui`
- **Authorization** — organization-scoped data access, plan limit bypass
- **Injection** — SQL injection in raw SQLAlchemy queries (`ezop-platform`), prompt injection in stored event data
- **Data exposure** — cross-organization data leakage via API or UI
- **Dependency vulnerabilities** — in `requirements.txt`, `package.json`, or the Python SDK

Out of scope:

- Vulnerabilities in self-hosted infrastructure (database, reverse proxy) that the user controls
- Rate limiting on unauthenticated endpoints (by design for health checks)
- Issues requiring physical access to the host

## Security architecture notes

- API keys are stored as SHA-256 hashes — plaintext keys are never persisted
- All data is scoped to `organization_id` — enforced at the query level in both `ezop-platform` and `ezop-light-ui`
- `ezop-platform` authenticates every request via `Authorization: Bearer <API_KEY>` before any data access
- `ezop-light-ui` uses NextAuth v5 with Google OAuth — no passwords are stored

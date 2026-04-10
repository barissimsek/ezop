# Ezop

Ezop is a vendor-agnostic, open-source **AI agent observability and audit platform**. It tracks agent registrations, versions, runs, spans, and events to give full visibility into every agent deployment — intent, decisions, tool usage, and failures.

## Repository Structure

This is a monorepo with three projects:

- **`ezop-light-ui/`** — The dashboard. A Next.js app that serves both the frontend and its own backend (server components, server actions, API routes). Uses Prisma + PostgreSQL directly.
- **`ezop-platform/`** — The API server for SDK clients. A FastAPI (Python) REST API that SDK agents send runs, spans, and events to. Enforces plan limits, stores data in PostgreSQL.
- **`ezop-sdk/`** — The SDK project. Currently contains only a Python SDK under `ezop-sdk/python/`.

## Key Facts

- The database is PostgreSQL. `ezop-light-ui` accesses it via Prisma. `ezop-platform` accesses it directly via SQLAlchemy/asyncpg.
- The Prisma schema lives in `ezop-light-ui/prisma/schema.prisma` and is the source of truth for the DB schema.
- Database migrations are under ezop-platform/database/migrations. - Authentication in `ezop-light-ui` uses NextAuth v5 (Auth.js) with Google OAuth as the primary provider.

## Workflows to follow

- After generating Prisma migrations, also create them in the specified folder and update `ezop-platform/database/current/` to reflect the latest database schema.
- Place migrations under the `ezop-platform/database/migrations/YYYY/` folder.
- Always review tests after making any changes. Update existing tests if interfaces change, and add new tests when introducing important functionality.
- Platform API changes are tightly coupled to SDK client interfaces. Keep them in sync—changes in one often require changes in the other. Always evaluate updates with this in mind.
- Big structural changes must include a design spec and a plan generated via `superpower::brainstorm`.
- Never commit or merge changes, neither create pull requests programmatically. Let developer handle those manually and safely.
- When there is SDK interface change, always update `ezop-sdk/python/pyproject.toml` and bump up the version.

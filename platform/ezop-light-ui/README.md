# Ezop Light UI

An open-source dashboard for AI agent observability. Monitor agent runs, inspect reasoning traces, manage API keys, and audit activity — all in one place.

## Features

- **Agent Inventory** — browse and manage your AI agents
- **Observability** — agent performance metrics, reasoning traces, and event logs
- **API Key Management** — create, revoke, and delete scoped API keys
- **Audit Logs** — full activity history for your organization
- **Multi-tenant** — organization-based access control with owner/member roles
- **Google OAuth** — sign in with Google

## Tech Stack

- [Next.js 16](https://nextjs.org) (App Router, Server Actions)
- [Prisma 7](https://prisma.io) with PostgreSQL
- [NextAuth v5](https://authjs.dev)
- [Recharts](https://recharts.org)

## Quick Start

**Prerequisites:** Node.js 22+, PostgreSQL 14+

```bash
git clone https://github.com/your-org/ezop-light-ui.git
cd ezop-light-ui
npm install
cp .env.example .env.local
```

Edit `.env.local` with your credentials, then:

```bash
npx prisma db push   # apply schema to your database
npm run dev          # start at http://localhost:3000
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full setup instructions.

## Environment Variables

| Variable | Description |
|---|---|
| `AUTH_SECRET` | Random secret for NextAuth (`npx auth secret`) |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `RESEND_API_KEY` | [Resend](https://resend.com) API key for email |
| `DATABASE_URL` | PostgreSQL connection string |

## Docker

```bash
docker build -t ezop-light-ui .
docker run -p 3000:3000 \
  -e DATABASE_URL=postgresql://user:pass@host:5432/db \
  -e AUTH_SECRET=... \
  -e GOOGLE_CLIENT_ID=... \
  -e GOOGLE_CLIENT_SECRET=... \
  -e RESEND_API_KEY=... \
  ezop-light-ui
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0 — see [LICENSE](LICENSE).

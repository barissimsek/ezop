# Contributing to ezop-light-ui

Thank you for your interest in contributing!

## Prerequisites

- Node.js 22+
- PostgreSQL 14+
- A Google OAuth app ([Google Cloud Console](https://console.cloud.google.com))
- A [Resend](https://resend.com) account for email

## Local Setup

1. **Clone and install**

   ```bash
   git clone https://github.com/your-org/ezop-light-ui.git
   cd ezop-light-ui
   npm install
   ```

2. **Configure environment**

   ```bash
   cp .env.example .env.local
   ```

   Fill in the values in `.env.local`:

   | Variable | How to get it |
   |---|---|
   | `AUTH_SECRET` | Run `npx auth secret` |
   | `GOOGLE_CLIENT_ID` | Google Cloud Console → APIs & Services → Credentials |
   | `GOOGLE_CLIENT_SECRET` | Same as above |
   | `RESEND_API_KEY` | [resend.com/api-keys](https://resend.com/api-keys) |
   | `DATABASE_URL` | Your PostgreSQL connection string |

3. **Set up the database**

   Create a PostgreSQL database and run the schema:

   ```bash
   npx prisma db push
   ```

4. **Install git hooks**

   ```bash
   npx lefthook install
   ```

   This sets up pre-commit (lint + typecheck) and pre-push (build) hooks.

5. **Start the dev server**

   ```bash
   npm run dev
   ```

   Open [http://localhost:3000](http://localhost:3000).

## Database Schema Changes

If you change the database schema, sync Prisma after:

```bash
npx prisma db pull    # updates prisma/schema.prisma from the live DB
npx prisma generate   # regenerates the TypeScript client
```

## Running E2E Tests

Tests use Playwright against a real database. Set `AUTH_TEST_SECRET` to any string in `.env.local` to enable the test credentials provider, then:

```bash
npm run test:e2e         # headless
npm run test:e2e:ui      # interactive UI
```

The test suite seeds and tears down its own data using fixed UUIDs, so it is safe to run against your local dev database.

## Code Style

- Run `npm run lint` before submitting — the CI enforces zero warnings.
- Follow the existing patterns: Server Components for data fetching, Server Actions for mutations, inline styles (no CSS modules or Tailwind).

## Submitting a Pull Request

1. Fork the repo and create a branch from `main`.
2. Make your changes with focused, descriptive commits.
3. Ensure `npm run lint` and `npm run build` pass locally.
4. Open a pull request against `main` with a clear description of what and why.

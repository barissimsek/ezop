import { test as setup, expect } from "@playwright/test"
import { prisma } from "../lib/prisma"
import path from "path"
import dotenv from "dotenv"
dotenv.config({ path: ".env.local" })
dotenv.config()

export { TEST_USER_ID, TEST_ORG_ID, TEST_AGENT_ID, TEST_RUN_ID, TEST_KEY_ID, TEST_USER_EMAIL } from "./constants"
import { TEST_USER_ID, TEST_ORG_ID, TEST_AGENT_ID, TEST_RUN_ID, TEST_KEY_ID, TEST_USER_EMAIL } from "./constants"

const SESSION_FILE = path.join(__dirname, ".auth/session.json")

setup("seed database and authenticate", async ({ page }) => {
  if (!process.env.AUTH_TEST_SECRET) throw new Error("AUTH_TEST_SECRET is not set")

  // ── Seed test data ────────────────────────────────────────────────────────
  await prisma.user.upsert({
    where:  { id: TEST_USER_ID },
    update: {},
    create: { id: TEST_USER_ID, email: TEST_USER_EMAIL, firstname: "Test", lastname: "User" },
  })

  await prisma.organization.upsert({
    where:  { id: TEST_ORG_ID },
    update: {},
    create: { id: TEST_ORG_ID, name: "Test Org" },
  })

  await prisma.organizationMember.upsert({
    where:  { user_id_organization_id: { user_id: TEST_USER_ID, organization_id: TEST_ORG_ID } },
    update: {},
    create: { user_id: TEST_USER_ID, organization_id: TEST_ORG_ID, role: "owner" },
  })

  await prisma.agent.upsert({
    where:  { id: TEST_AGENT_ID },
    update: {},
    create: { id: TEST_AGENT_ID, name: "TestAgent", owner: TEST_USER_EMAIL, description: "Playwright test agent", runtime: "python/test", organization_id: TEST_ORG_ID },
  })

  await prisma.agentRun.upsert({
    where:  { id: TEST_RUN_ID },
    update: {},
    create: { id: TEST_RUN_ID, agent_id: TEST_AGENT_ID, organization_id: TEST_ORG_ID, status: "success", start_time: new Date(Date.now() - 60000), end_time: new Date() },
  })

  await prisma.apiKey.upsert({
    where:  { id: TEST_KEY_ID },
    update: {},
    create: { id: TEST_KEY_ID, name: "Test Key", description: "Playwright test key", key_prefix: "ezop_sk_playwright", key_hash: "testhash", scopes: ["read"], organization_id: TEST_ORG_ID, created_by: TEST_USER_ID },
  })

  await prisma.$disconnect()

  // ── Authenticate ──────────────────────────────────────────────────────────
  await page.goto("/api/auth/signin")

  await page.locator('input[name="secret"]').fill(process.env.AUTH_TEST_SECRET)
  await page.locator('#submitButton').click()

  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })

  await page.context().storageState({ path: SESSION_FILE })
})

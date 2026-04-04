import { test, expect } from "../fixtures"

test.describe("API Key Management", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/dashboard/api-keys")
  })

  test("renders the API keys page", async ({ page }) => {
    await expect(page.locator("h1")).toContainText("API Keys")
  })

  test("shows seeded test key in the table", async ({ page }) => {
    await expect(page.getByText("Test Key", { exact: true })).toBeVisible()
    await expect(page.getByText("ezop_sk_playwright")).toBeVisible()
  })

  test("create key dialog opens and closes", async ({ page }) => {
    await page.getByRole("button", { name: /create api key/i }).click()
    await expect(page.getByRole("heading", { name: "Create API Key" })).toBeVisible()

    // Cancel
    await page.getByRole("button", { name: /cancel/i }).click()
    await expect(page.getByRole("heading", { name: "Create API Key" })).not.toBeVisible()
  })

  test("create key form requires a name", async ({ page }) => {
    await page.getByRole("button", { name: /create api key/i }).click()
    // Submit without filling name — dialog should stay open
    await page.getByRole("button", { name: "Create Key" }).click()
    // Modal should remain visible (validation blocked submit)
    await expect(page.getByRole("heading", { name: "Create API Key" })).toBeVisible()
    await page.getByRole("button", { name: /cancel/i }).click()
  })

  test("creating a key shows the revealed key banner", async ({ page }) => {
    await page.getByRole("button", { name: /create api key/i }).click()

    await page.locator("input[placeholder='e.g. Production Backend']").fill("E2E Test Key")
    await page.getByRole("button", { name: "Create Key" }).click()

    // Banner with the raw key should appear
    await expect(page.getByText(/ezop_sk_/)).toBeVisible({ timeout: 10000 })
  })

  test("revoking a key shows revoked status", async ({ page }) => {
    // Use the seeded key prefix to find the exact row
    const row = page.locator("tr, [style*='grid']").filter({ hasText: "ezop_sk_playwright" })
    await row.getByRole("button", { name: /revoke/i }).click()

    // Confirm in the dialog
    await page.getByRole("button", { name: "Revoke" }).last().click()

    await expect(page.getByText(/revoked/i)).toBeVisible({ timeout: 5000 })
  })

  test("delete button appears on revoked key", async ({ page }) => {
    // The seeded key may already be revoked by the previous test — either way, Delete should be visible
    const row = page.locator("tr, [style*='grid']").filter({ hasText: "ezop_sk_playwright" })
    const revokeBtn = row.getByRole("button", { name: /revoke/i })
    if (await revokeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await revokeBtn.click()
      await page.getByRole("button", { name: "Revoke" }).last().click()
    }
    await expect(row.getByRole("button", { name: /delete/i })).toBeVisible({ timeout: 5000 })
  })
})

test.describe("API Keys — navigation", () => {
  test("sidebar link navigates to API keys page", async ({ page }) => {
    await page.goto("/dashboard")
    await page.getByRole("link", { name: /api keys/i }).click()
    await expect(page).toHaveURL(/api-keys/)
    await expect(page.locator("h1")).toContainText("API Keys")
  })
})

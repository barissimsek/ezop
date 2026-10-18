import { test, expect } from "../fixtures"

test.describe("Onboarding", () => {
  test("authenticated user sees onboarding form", async ({ page }) => {
    await page.goto("/onboarding")
    await expect(page).toHaveURL(/\/onboarding/)
  })

  test("onboarding form shows workspace setup step", async ({ page }) => {
    await page.goto("/onboarding")
    await expect(page.getByText("Welcome! Let's set up your workspace")).toBeVisible()
  })

  test("onboarding requires authentication", async ({ browser }) => {
    const freshContext = await browser.newContext({ storageState: { cookies: [], origins: [] } })
    const freshPage = await freshContext.newPage()

    // Without auth, /onboarding redirects to /
    await freshPage.goto("/onboarding")
    await expect(freshPage).toHaveURL("/")

    await freshPage.close()
    await freshContext.close()
  })
})

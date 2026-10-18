import { test, expect } from "@playwright/test"

// These tests run without authentication (override storageState)
test.use({ storageState: { cookies: [], origins: [] } })

test.describe("Login page", () => {
  test("shows sign-in button", async ({ page }) => {
    await page.goto("/")
    await expect(page.locator("button[type=submit]")).toBeVisible()
  })

  test("unauthenticated access to /dashboard redirects to /", async ({ page }) => {
    await page.goto("/dashboard")
    await expect(page).toHaveURL("/")
  })

  test("unauthenticated access to /onboarding redirects to /", async ({ page }) => {
    await page.goto("/onboarding")
    await expect(page).toHaveURL("/")
  })
})

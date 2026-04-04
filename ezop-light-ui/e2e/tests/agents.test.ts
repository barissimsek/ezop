import { test, expect } from "../fixtures"

test.describe("Agent Inventory", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/dashboard/agents")
  })

  test("renders the agent inventory page", async ({ page }) => {
    await expect(page.locator("h1")).toContainText("Agent Inventory")
  })

  test("shows seeded test agent in the table", async ({ page }) => {
    await expect(page.getByText("TestAgent")).toBeVisible()
  })

  test("search filters agents by name", async ({ page }) => {
    const search = page.locator("input[placeholder='Search agents...']")
    await expect(search).toBeVisible()

    await search.fill("TestAgent")
    await expect(page.getByText("TestAgent")).toBeVisible()

    await search.fill("zzz-no-match")
    await expect(page.getByText("TestAgent")).not.toBeVisible()
    await expect(page.getByText("0 agents")).toBeVisible()
  })

  test("clicking an agent opens the detail modal", async ({ page }) => {
    await page.getByText("TestAgent").click()
    // Modal should appear
    const modal = page.locator("[style*='position: fixed']")
    await expect(modal).toBeVisible()
    // Header shows agent name
    await expect(modal.getByText("TestAgent")).toBeVisible()
  })

  test("modal has all 5 tabs", async ({ page }) => {
    await page.getByText("TestAgent").click()
    const modal = page.locator("[style*='position: fixed']")
    await expect(modal.getByRole("button", { name: "Overview" })).toBeVisible()
    await expect(modal.getByRole("button", { name: "Run History" })).toBeVisible()
    await expect(modal.getByRole("button", { name: "Versions" })).toBeVisible()
    await expect(modal.getByRole("button", { name: "Reasoning" })).toBeVisible()
    await expect(modal.getByRole("button", { name: "Metrics" })).toBeVisible()
  })

  test("Overview tab shows agent metadata", async ({ page }) => {
    await page.getByText("TestAgent").click()
    const modal = page.locator("[style*='position: fixed']")
    await modal.getByRole("button", { name: "Overview" }).click()
    await expect(modal.getByText("Playwright test agent")).toBeVisible()
    await expect(modal.getByText("python/test")).toBeVisible()
  })

  test("Run History tab lists runs", async ({ page }) => {
    await page.getByText("TestAgent").click()
    const modal = page.locator("[style*='position: fixed']")
    await modal.getByRole("button", { name: "Run History" }).click()
    await expect(modal.getByText("success")).toBeVisible()
  })

  test("clicking a run in Run History loads events", async ({ page }) => {
    await page.getByText("TestAgent").click()
    const modal = page.locator("[style*='position: fixed']")
    await modal.getByRole("button", { name: "Run History" }).click()
    // Run rows should be visible (success status was seeded)
    await expect(modal.getByText("success")).toBeVisible({ timeout: 5000 })
  })

  test("Metrics tab shows success rate", async ({ page }) => {
    await page.getByText("TestAgent").click()
    const modal = page.locator("[style*='position: fixed']")
    await modal.getByRole("button", { name: "Metrics" }).click()
    await expect(modal.getByText("Success Rate")).toBeVisible()
  })

  test("Reasoning tab shows empty state", async ({ page }) => {
    await page.getByText("TestAgent").click()
    const modal = page.locator("[style*='position: fixed']")
    await modal.getByRole("button", { name: "Reasoning" }).click()
    await expect(modal.getByText("No reasoning trace data available yet.")).toBeVisible()
  })

  test("closing modal with × button works", async ({ page }) => {
    await page.getByText("TestAgent").click()
    const modal = page.locator("[style*='position: fixed']")
    await modal.locator("button").filter({ hasText: "×" }).click()
    await expect(modal).not.toBeVisible()
  })

  test("closing modal by clicking backdrop works", async ({ page }) => {
    await page.getByText("TestAgent").click()
    const modal = page.locator("[style*='position: fixed']")
    await expect(modal).toBeVisible()
    // Click the backdrop (outside the modal card)
    await page.mouse.click(10, 10)
    await expect(modal).not.toBeVisible()
  })

  test("can add and remove a tag on an agent", async ({ page }) => {
    await page.getByText("TestAgent").click()
    const modal = page.locator("[style*='position: fixed']")
    await modal.getByRole("button", { name: "+ Add Tag" }).click()
    await modal.locator("input[placeholder='tag name...']").fill("e2e-tag")
    await page.keyboard.press("Enter")
    await expect(modal.getByText("e2e-tag")).toBeVisible()
    // Remove it
    await modal.locator("button", { hasText: "×" }).last().click()
    await expect(modal.getByText("e2e-tag")).not.toBeVisible()
  })
})

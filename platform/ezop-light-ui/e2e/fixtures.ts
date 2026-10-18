import { test as base, expect, Page } from "@playwright/test"

// Re-export expect for convenience
export { expect }

// Fixture: page already authenticated (storage state set in playwright.config.ts)
// No extra setup needed — just re-export with the right type

export const test = base.extend<{ authenticatedPage: Page }>({
  authenticatedPage: async ({ page }, use) => {
    await use(page)
  },
})

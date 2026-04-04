import { defineConfig, devices } from "@playwright/test"
import dotenv from "dotenv"
dotenv.config({ path: ".env.local" })
dotenv.config()

export default defineConfig({
  testDir: "./e2e/tests",
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],

  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "setup",
      testDir: "./e2e",
      testMatch: "global-setup.ts",
    },
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: "e2e/.auth/session.json",
      },
      dependencies: ["setup"],
      teardown: "teardown",
    },
    {
      name: "teardown",
      testDir: "./e2e",
      testMatch: "global-teardown.ts",
    },
  ],

  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      AUTH_SECRET: process.env.AUTH_SECRET ?? "playwright-dev-secret-32-chars-min",
      AUTH_TEST_SECRET: process.env.AUTH_TEST_SECRET ?? "",
      DATABASE_URL: process.env.DATABASE_URL ?? "",
    },
  },
})

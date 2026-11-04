import { defineConfig, devices } from "@playwright/test";

/**
 * E2E and screenshot suites run against a RUNNING local stack (`make dev` + `make seed`), i.e. the real local
 * model and live web search. They are therefore not part of ordinary CI; see docs/DEMO.md.
 */
const baseURL = process.env.NEXUS_WEB_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  timeout: 6 * 60_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL, trace: "retain-on-failure", reducedMotion: "reduce" },
  projects: [
    { name: "e2e", testMatch: /journey\.spec\.ts/, use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "screenshots", testMatch: /screenshots\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
  ],
});

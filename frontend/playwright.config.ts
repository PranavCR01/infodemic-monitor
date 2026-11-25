import { defineConfig, devices } from "@playwright/test";

// Smoke suite against a DEPLOYED frontend + backend (staging / Vercel preview).
// Nothing here runs in CI: every test skips unless E2E_BASE_URL and the test
// account are set. See e2e/README.md.
export default defineConfig({
  testDir: "./e2e",
  timeout: (Number(process.env.E2E_TIMEOUT_MINUTES) || 10) * 60_000 + 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { outputFolder: "e2e-report", open: "never" }]],
  outputDir: "e2e-results",
  use: {
    baseURL: process.env.E2E_BASE_URL,
    trace: "off",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
        launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
      },
    },
  ],
});

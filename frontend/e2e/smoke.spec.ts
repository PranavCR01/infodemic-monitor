import { existsSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// End-to-end smoke test of the analyst journey on a deployed environment:
// sign in → upload → progress → result → claim drawer → export.
// Configure with environment variables only (never commit credentials):
//   E2E_BASE_URL        e.g. https://infodemic-monitor-git-xyz.vercel.app
//   E2E_EMAIL           a test analyst account (password sign-in enabled)
//   E2E_PASSWORD
//   E2E_VIDEO           path to a short MP4/MOV (under 3 minutes, under 100 MB)
//   E2E_TIMEOUT_MINUTES how long to wait for the analysis (default 10)

const env = {
  base: process.env.E2E_BASE_URL,
  email: process.env.E2E_EMAIL,
  password: process.env.E2E_PASSWORD,
  video: process.env.E2E_VIDEO,
  minutes: Number(process.env.E2E_TIMEOUT_MINUTES) || 10,
};
const missing = (["base", "email", "password", "video"] as const).filter((k) => !env[k]);

// Internal names that must never reach the screen (brief: "internal names never shown").
const INTERNAL = /\b(NO_MISINFO|DEBUNKING|CANNOT_RECOGNIZE|INSUFFICIENT_EVIDENCE|NOT_VERIFIABLE|REVIEW_REQUIRED|RETRY_PENDING)\b|\b(weak_evidence|judge):/;

async function noInternalNames(page: Page) {
  const text = await page.locator("main").innerText();
  expect(text, "internal enum or reason code on screen").not.toMatch(INTERNAL);
}

test.describe("analyst smoke test", () => {
  test.skip(missing.length > 0, `set ${missing.map((k) => ({ base: "E2E_BASE_URL", email: "E2E_EMAIL", password: "E2E_PASSWORD", video: "E2E_VIDEO" })[k]).join(", ")} to run`);

  test("sign in, upload, follow progress, read the result, open a claim, export", async ({ page }, info) => {
    const shot = async (name: string) => info.attach(name, { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });
    const consoleErrors: string[] = [];
    page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

    await test.step("sign in", async () => {
      await page.goto("/sign-in");
      await page.getByLabel("Email").fill(env.email!);
      await page.getByLabel("Password").fill(env.password!);
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      await expect(page).not.toHaveURL(/\/sign-in/);
      await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
    });

    let jobUrl = "";
    await test.step("upload a video and start the analysis", async () => {
      expect(existsSync(env.video!), `E2E_VIDEO not found: ${env.video}`).toBe(true);
      await page.goto("/");
      await page.locator("#file").setInputFiles(env.video!);
      await expect(page.getByText(/^Uploaded/)).toBeVisible({ timeout: 5 * 60_000 });
      await shot("uploaded");
      await page.getByRole("button", { name: "Start analysis" }).click();
      await page.waitForURL(/\/jobs\/[^/]+$/);
      jobUrl = page.url();
    });

    await test.step("follow progress until the result", async () => {
      const result = page.getByRole("heading", { name: "Assessment" });
      const failed = page.getByRole("heading", { name: "The analysis didn't finish" });
      await expect(result.or(failed)).toBeVisible({ timeout: env.minutes * 60_000 });
      if (await failed.isVisible()) {
        await shot("failed");
        throw new Error(`analysis failed: ${await page.locator("main").innerText()}`);
      }
      await shot("result");
    });

    await test.step("read the result", async () => {
      // A label, its description, and no confidence number.
      await expect(page.locator("[data-label]").first()).toBeVisible();
      await expect(page.getByText("Not yet calibrated.", { exact: false })).toBeVisible();
      await noInternalNames(page);
    });

    await test.step("open a claim and close it again", async () => {
      const details = page.getByRole("button", { name: /details/i }).first();
      if ((await details.count()) === 0) {
        info.annotations.push({ type: "note", description: "result has no claims (single-call or no-claims result); drawer step skipped" });
        return;
      }
      await details.click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      await expect(page).toHaveURL(/[?&]claim=/);
      await expect(dialog.getByText(/^Claim \d+ of \d+$/)).toBeVisible();
      await shot("claim drawer");
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
      await expect(details).toBeFocused();
    });

    await test.step("export the report", async () => {
      await page.getByRole("link", { name: /Export report/ }).click();
      await page.waitForURL(/\/export$/);
      await expect(page.getByText("Video assessment report", { exact: false })).toBeVisible();
      await noInternalNames(page);
      await page.emulateMedia({ media: "print" });
      await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
      info.attach("report.pdf", { body: await page.pdf({ format: "Letter", printBackground: true }), contentType: "application/pdf" });
      await page.emulateMedia({ media: "screen" });
    });

    await test.step("job appears in the list", async () => {
      await page.goto("/jobs");
      const id = jobUrl.split("/").pop()!;
      await expect(page.locator(`a[href="/jobs/${id}"]`)).toBeVisible();
    });

    expect(consoleErrors, "browser console errors").toEqual([]);
  });
});

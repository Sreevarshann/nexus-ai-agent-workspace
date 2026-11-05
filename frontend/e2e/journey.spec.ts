import path from "node:path";

import { expect, test } from "@playwright/test";

import { SAMPLES } from "./helpers";

/**
 * The full acceptance journey against the real stack (local LLM + live web).
 * A fresh account is created per run so the test never depends on prior data.
 */
test("NEXUS end-to-end journey", async ({ page }) => {
  const email = `e2e-${Date.now()}@nexus.local`;
  const password = `e2e-${Math.random().toString(36).slice(2)}-pw`;

  await test.step("1. register and open the workspace", async () => {
    await page.goto("/register");
    await page.getByLabel("Name").fill("E2E Tester");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: /Create workspace/ }).click();
    await expect(page.getByRole("heading", { name: /What should we/ })).toBeVisible();
  });

  await test.step("2. create a project", async () => {
    await page.getByRole("button", { name: "Switch project" }).click();
    await page.getByRole("menuitem", { name: "New project" }).click();
    await page.getByLabel("Project name").fill("E2E Project");
    await page.getByRole("button", { name: "Create project" }).click();
    await expect(page.getByRole("button", { name: "Switch project" })).toContainText("E2E Project");
  });

  let conversationUrl = "";
  await test.step("3-4. start a conversation and stream a real LLM reply", async () => {
    await page.getByRole("textbox", { name: "Message" }).fill("In one sentence, what is a vector database?");
    await page.keyboard.press("Enter");
    await page.waitForURL(/\/workspace\/[0-9a-f-]{36}/);
    conversationUrl = page.url();
    await expect(page.getByRole("button", { name: "Regenerate response" })).toBeVisible({ timeout: 120_000 });
    await expect(page.locator(".nx-prose").last()).toContainText(/vector/i);
  });

  await test.step("5-6. upload a document and inspect a real citation", async () => {
    await page.goto("/library");
    await page.locator('input[type="file"]').setInputFiles(path.join(SAMPLES, "documents/helios-grid-whitepaper.pdf"));
    await expect(page.getByRole("button", { name: /helios-grid-whitepaper\.pdf/ }).getByText("Ready")).toBeVisible({ timeout: 120_000 });
    await page.goto("/workspace");
    await page.getByRole("switch", { name: "Search my whole library" }).click();
    await page.getByRole("textbox", { name: "Message" }).fill("What round-trip efficiency did the Helios Grid pilot achieve?");
    await page.keyboard.press("Enter");
    const chip = page.getByRole("button", { name: /^Citation S\d+$/ }).first();
    await expect(chip).toBeVisible({ timeout: 150_000 });
    await chip.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("helios-grid-whitepaper.pdf");
    await expect(dialog.locator("blockquote")).not.toBeEmpty();
    await page.keyboard.press("Escape");
  });

  await test.step("7-8. upload a dataset and compute an interactive chart", async () => {
    await page.goto("/data");
    await page.locator('input[type="file"]').setInputFiles(path.join(SAMPLES, "datasets/synthetic_sales_2023_2025.csv"));
    await expect(page.getByText("9,557", { exact: true })).toBeVisible({ timeout: 60_000 });
    await page.getByRole("tab", { name: /Chart builder/ }).click();
    await page.getByRole("button", { name: /Compute chart/ }).click();
    await expect(page.getByTestId("chart").first()).toBeVisible();
    await expect(page.locator(".recharts-surface").first()).toBeVisible();
  });

  let missionUrl = "";
  await test.step("9-10. run an agent mission and inspect tool events", async () => {
    await page.goto("/research");
    await page.getByLabel("Research question").fill("What is the Model Context Protocol and who maintains it?");
    await page.getByRole("radio", { name: /Quick Research/ }).click();
    await page.getByRole("switch", { name: /Require approval/ }).click(); // off: run straight through
    await page.getByRole("button", { name: /Launch mission/ }).click();
    await page.waitForURL(/\/missions\/[0-9a-f-]{36}/);
    missionUrl = page.url();
    await expect(page.getByTestId("node-planner")).toHaveAttribute("data-status", "completed", { timeout: 120_000 });
    await expect(page.getByTestId("node-final").first()).toHaveAttribute("data-status", "completed", { timeout: 300_000 });
    await page.getByRole("tab", { name: /Tools/ }).click();
    await expect(page.getByText("web_search").first()).toBeVisible();
    await expect(page.getByText("fetch_url").first()).toBeVisible();
  });

  await test.step("11. open and download the generated artifact", async () => {
    await page.getByRole("link", { name: /View report/ }).click();
    await expect(page.getByText("Verified against retrieved evidence").or(page.locator("article h1"))).toBeVisible();
    const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "MD" }).click()]);
    expect(dl.suggestedFilename()).toMatch(/\.md$/);
    const [pdf] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "PDF" }).click()]);
    expect(pdf.suggestedFilename()).toMatch(/\.pdf$/);
  });

  await test.step("12. reload and verify persistence", async () => {
    await page.goto(conversationUrl);
    await page.reload();
    await expect(page.locator(".nx-prose").first()).toContainText(/vector/i);
    await page.goto(missionUrl);
    await page.reload();
    await expect(page.getByTestId("node-final").first()).toHaveAttribute("data-status", "completed");
  });
});

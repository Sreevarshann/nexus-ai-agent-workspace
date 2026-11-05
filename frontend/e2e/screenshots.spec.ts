import fs from "node:fs";
import path from "node:path";

import { expect, type Page, test } from "@playwright/test";

import { demoCredentials, ROOT, signIn } from "./helpers";

/** Captures real screenshots of the running app (seeded demo account) into docs/screenshots. */
const OUT = path.join(ROOT, "docs/screenshots");
const VIEWPORTS = { "1920": { width: 1920, height: 1080 }, "1440": { width: 1440, height: 900 }, tablet: { width: 768, height: 1024 }, mobile: { width: 390, height: 844 } };

async function shot(page: Page, name: string) {
  // SKIP_EXISTING=1 resumes an interrupted capture without re-shooting finished images
  if (process.env.SKIP_EXISTING && fs.existsSync(path.join(OUT, `${name}.png`))) return;
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });
}

test("capture product screenshots", async ({ page, browser }) => {
  test.setTimeout(45 * 60_000);
  await page.setViewportSize(VIEWPORTS["1440"]);
  await page.goto("/login");
  await shot(page, "login");
  const { email, password } = demoCredentials();
  await signIn(page, email, password);

  for (const [vp, size] of Object.entries(VIEWPORTS)) {
    await page.setViewportSize(size);
    await page.goto("/workspace");
    await expect(page.getByRole("heading", { name: /What should we/ })).toBeVisible();
    await shot(page, `workspace-home-${vp}`);
  }
  await page.setViewportSize(VIEWPORTS["1440"]);

  const api = page.request;
  const convs = await (await api.get("/api/conversations")).json();
  const cited = [];
  for (const c of convs) {
    const msgs = await (await api.get(`/api/conversations/${c.id}/messages`)).json();
    if (msgs.some((m: { citations: unknown[] }) => m.citations?.length)) cited.push(c.id);
  }
  if (cited[0]) {
    await page.goto(`/workspace/${cited[0]}`);
    await expect(page.locator(".nx-prose").first()).toBeVisible();
    const chip = page.getByRole("button", { name: /^Citation S\d+$/ }).first();
    await chip.scrollIntoViewIfNeeded();
    await chip.click(); // also selects that answer, filling the evidence panel
    await shot(page, "citation-inspector");
    await page.keyboard.press("Escape");
    await chip.scrollIntoViewIfNeeded();
    await shot(page, "workspace-conversation-1440");
  }

  const tasks = await (await api.get("/api/tasks?kind=mission")).json();
  const done = tasks.find((t: { status: string; mode: string }) => t.status === "completed" && t.mode === "compare") ?? tasks.find((t: { status: string }) => t.status === "completed");
  if (done) {
    for (const vp of ["1920", "1440"] as const) {
      await page.setViewportSize(VIEWPORTS[vp]);
      await page.goto(`/missions/${done.id}`);
      await expect(page.getByTestId("node-planner").first()).toBeVisible();
      await shot(page, `mission-control-${vp}`);
    }
    await page.getByTestId("node-web_researcher").first().click();
    await shot(page, "mission-inspector-sources");
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.goto(`/missions/${done.id}`);
    await shot(page, "mission-control-mobile");
    await page.setViewportSize(VIEWPORTS["1440"]);
    const detail = await (await api.get(`/api/tasks/${done.id}/detail`)).json();
    if (detail.artifacts[0]) {
      await page.goto(`/artifacts/${detail.artifacts[0].id}`);
      await expect(page.locator("article h1")).toBeVisible();
      await shot(page, "artifact-report");
    }
  }
  await page.goto("/missions");
  await shot(page, "missions-list");
  await page.goto("/research");
  await shot(page, "research-studio");
  await page.goto("/library");
  await page.waitForTimeout(2500);
  await shot(page, "knowledge-library");
  await page.goto("/data");
  await expect(page.getByText("Rows")).toBeVisible();
  await page.getByRole("tab", { name: /Profile/ }).click();
  await shot(page, "data-lab-profile");
  await page.getByRole("tab", { name: /Chart builder/ }).click();
  await page.getByRole("button", { name: /Compute chart/ }).click();
  await expect(page.locator(".recharts-surface").first()).toBeVisible();
  await shot(page, "data-lab-chart");
  await page.setViewportSize(VIEWPORTS.tablet);
  await shot(page, "data-lab-tablet");
  await page.setViewportSize(VIEWPORTS["1440"]);
  const wfs = await (await api.get("/api/workflows")).json();
  if (wfs[0]) {
    await page.goto(`/workflows/${wfs[0].id}`);
    await expect(page.locator(".react-flow__node").first()).toBeVisible();
    await shot(page, "workflow-builder");
  }
  await page.goto("/settings");
  await shot(page, "settings-model");
  await page.getByRole("tab", { name: /MCP connectors/ }).click();
  await shot(page, "settings-mcp");
  await page.setViewportSize(VIEWPORTS.mobile);
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await shot(page, "mobile-navigation");
  await page.keyboard.press("Escape");
  await page.setViewportSize(VIEWPORTS["1440"]);
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByRole("dialog")).toBeVisible();
  await shot(page, "command-palette");
  void browser;
});

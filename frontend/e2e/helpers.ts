import fs from "node:fs";
import path from "node:path";

import type { Page } from "@playwright/test";

export const ROOT = path.resolve(__dirname, "../..");
export const SAMPLES = path.join(ROOT, "samples");

export function demoCredentials(): { email: string; password: string } {
  const env = fs.readFileSync(path.join(ROOT, ".env"), "utf8");
  const get = (k: string) => env.match(new RegExp(`^${k}=(.*)$`, "m"))?.[1]?.trim();
  const email = get("NEXUS_DEMO_EMAIL");
  const password = get("NEXUS_DEMO_PASSWORD");
  if (!email || !password) throw new Error("Run `make seed` first: demo credentials are missing from .env");
  return { email, password };
}

export async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /Sign in/ }).click();
  await page.waitForURL(/\/workspace/);
}

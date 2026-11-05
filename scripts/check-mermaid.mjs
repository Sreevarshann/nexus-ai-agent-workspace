// Parse every ```mermaid block in README.md and docs/*.md with the official Mermaid parser.
// Usage: node scripts/check-mermaid.mjs   (installs nothing globally; uses a temp npx package)
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const files = ["README.md", ...fs.readdirSync(path.join(root, "docs")).filter((f) => f.endsWith(".md")).map((f) => `docs/${f}`)];
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mermaid-"));
let n = 0;
for (const f of files) {
  const p = path.join(root, f);
  if (!fs.existsSync(p)) continue;
  for (const m of fs.readFileSync(p, "utf8").matchAll(/```mermaid\n([\s\S]*?)```/g)) {
    fs.writeFileSync(path.join(dir, `${n++}-${path.basename(f, ".md")}.mmd`), m[1]);
  }
}
const runner = path.join(dir, "check.mjs");
fs.writeFileSync(runner, `
import fs from "node:fs";
import { JSDOM } from "jsdom";
const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const k of ["window", "document", "Element", "HTMLElement", "SVGElement", "Node", "DOMParser", "MutationObserver", "getComputedStyle"]) globalThis[k] = k === "window" ? dom.window : dom.window[k];
globalThis.window.SVGElement ??= dom.window.Element;
const { default: mermaid } = await import("mermaid");
mermaid.initialize({ startOnLoad: false });
let bad = 0;
for (const f of fs.readdirSync(${JSON.stringify(dir)}).filter((x) => x.endsWith(".mmd")).sort()) {
  try { await mermaid.parse(fs.readFileSync(${JSON.stringify(dir)} + "/" + f, "utf8")); console.log("ok  ", f); }
  catch (e) { bad++; console.error("FAIL", f, String(e.message ?? e).split("\\n")[0]); }
}
process.exit(bad ? 1 : 0);
`);
execFileSync("npm", ["install", "--silent", "--no-audit", "--no-fund", "--prefix", dir, "mermaid@11.4.1", "jsdom@25.0.1"], { stdio: "inherit" });
execFileSync("node", [runner], { stdio: "inherit", cwd: dir, env: { ...process.env, NODE_PATH: path.join(dir, "node_modules") } });
console.log(`${n} Mermaid diagrams valid`);

"""Create the local demo account and load the synthetic sample content through the real API.

The demo password is generated once and stored in the repository's gitignored `.env`
(NEXUS_DEMO_EMAIL / NEXUS_DEMO_PASSWORD). Re-running is idempotent.
"""

from __future__ import annotations

import os
import secrets
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env"
API = os.environ.get("NEXUS_API", "http://127.0.0.1:8010/api")


def env_value(key: str) -> str | None:
    if not ENV.exists():
        return None
    for line in ENV.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def ensure_credentials() -> tuple[str, str]:
    email = env_value("NEXUS_DEMO_EMAIL") or "demo@nexus.local"
    password = env_value("NEXUS_DEMO_PASSWORD")
    if not password:
        password = secrets.token_urlsafe(12)
        with ENV.open("a") as f:
            f.write(f"\n# Local demo account created by `make seed`\nNEXUS_DEMO_EMAIL={email}\nNEXUS_DEMO_PASSWORD={password}\n")
    return email, password


def main() -> None:
    email, password = ensure_credentials()
    c = httpx.Client(base_url=API, timeout=120)
    try:
        c.get("/health").raise_for_status()
    except httpx.HTTPError:
        sys.exit(f"API not reachable at {API}. Start it with `make dev` first.")
    r = c.post("/auth/login", json={"email": email, "password": password})
    if r.status_code == 401:
        r = c.post("/auth/register", json={"email": email, "name": "Demo Analyst", "password": password})
    r.raise_for_status()

    samples = ROOT / "samples"
    have_docs = {d["filename"] for d in c.get("/documents").json()}
    for f in sorted((samples / "documents").iterdir()):
        if f.name not in have_docs:
            c.post("/documents", files={"file": (f.name, f.read_bytes())}).raise_for_status()
            print("uploaded document", f.name)
    have_ds = {d["filename"] for d in c.get("/datasets").json()}
    for f in sorted((samples / "datasets").iterdir()):
        if f.name not in have_ds:
            c.post("/datasets", files={"file": (f.name, f.read_bytes())}, data={"name": "Synthetic sales 2023-2025"}).raise_for_status()
            print("uploaded dataset", f.name)
    if not c.get("/workflows").json():
        for tpl, name in (("web_research_report", "Web research brief"), ("document_qa", "Policy Q&A")):
            c.post("/workflows", json={"name": name, "template": tpl}).raise_for_status()
        print("created example workflows")
    for _ in range(60):
        docs = c.get("/documents").json()
        if all(d["status"] in ("ready", "failed") for d in docs):
            break
        time.sleep(1)
    print(f"Demo account ready: {email} (password in .env as NEXUS_DEMO_PASSWORD)")


if __name__ == "__main__":
    main()

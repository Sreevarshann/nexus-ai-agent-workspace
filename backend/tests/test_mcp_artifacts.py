import json

from httpx import AsyncClient

from tests.conftest import settle

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-06-18",
}


async def rpc(client: AsyncClient, token: str | None, method: str, params: dict | None = None, rid: int = 1):  # type: ignore[no-untyped-def]
    headers = dict(MCP_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return await client.post(
        "/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
    )


async def test_mcp_requires_token_and_serves_user_scoped_tools(client: AsyncClient, user: dict) -> None:
    from nexus.main import mcp

    async with mcp.session_manager.run():
        await _mcp_flow(client)


async def _mcp_flow(client: AsyncClient) -> None:
    assert (await rpc(client, None, "tools/list")).status_code == 401
    await client.post("/api/documents", files={"file": ("mcp.md", b"# MCP\n\nThe secret launch codename is BLUEBIRD.")})
    await settle()
    token = (await client.post("/api/auth/tokens", json={"name": "inspector"})).json()["token"]
    init = await rpc(
        client,
        token,
        "initialize",
        {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "1"}},
    )
    assert init.status_code == 200, init.text
    tools = (await rpc(client, token, "tools/list", rid=2)).json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"search_documents", "query_dataset", "get_citation", "get_task_status"} <= names
    assert "fetch_url" not in names and "web_search" not in names  # no external side-effect tools exposed

    call = (
        await rpc(
            client, token, "tools/call", {"name": "search_documents", "arguments": {"query": "launch codename"}}, rid=3
        )
    ).json()
    payload = call["result"].get("structuredContent") or json.loads(call["result"]["content"][0]["text"])
    assert "BLUEBIRD" in payload["hits"][0]["text"]
    stats = (await client.get("/api/system/tools")).json()
    assert stats["mcp"]["recent_calls"][0]["tool"] == "search_documents"


async def test_artifact_versions_and_exports(client: AsyncClient, user: dict) -> None:
    t = (await client.post("/api/tasks", json={"prompt": "Artifact export topic", "mode": "quick"})).json()
    await settle()
    aid = (await client.get(f"/api/tasks/{t['id']}/detail")).json()["artifacts"][0]["id"]
    for fmt, ctype, magic in (
        ("md", "text/markdown", b"# "),
        ("json", "application/json", b"{"),
        ("pdf", "application/pdf", b"%PDF"),
    ):
        r = await client.get(f"/api/artifacts/{aid}/export", params={"format": fmt})
        assert r.status_code == 200 and r.headers["content-type"].startswith(ctype) and r.content.startswith(magic)
    assert (await client.get(f"/api/artifacts/{aid}/export", params={"format": "csv"})).status_code == 422
    v2 = (
        await client.post(f"/api/artifacts/{aid}/versions", json={"content": "## Edited\n\nNew body", "note": "edit"})
    ).json()
    assert v2["version"] == 2
    art = (await client.get(f"/api/artifacts/{aid}")).json()
    assert art["current_version"] == 2 and [v["version"] for v in art["versions"]] == [1, 2]
    v1 = (await client.get(f"/api/artifacts/{aid}/versions/1")).json()
    assert v1["content"] != "## Edited\n\nNew body"


async def test_health_and_metrics(client: AsyncClient, user: dict) -> None:
    h = (await client.get("/api/health")).json()
    assert h["checks"]["database"]["ok"] and h["checks"]["llm"]["provider"] == "fixture"
    m = (await client.get("/api/system/metrics")).json()
    assert {"tools", "tasks", "generation", "sources"} <= set(m)

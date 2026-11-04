from httpx import AsyncClient

from tests.conftest import read_sse, settle


async def send(client: AsyncClient, content: str, **kw) -> tuple[str, dict, dict]:  # type: ignore[no-untyped-def]
    conv = (await client.post("/api/conversations", json={})).json()
    msgs = (await client.post(f"/api/conversations/{conv['id']}/messages", json={"content": content, **kw})).json()
    return conv["id"], msgs[0], msgs[1]


async def test_streamed_reply_is_persisted(client: AsyncClient, user: dict) -> None:
    cid, u, a = await send(client, "Hello there NEXUS")
    assert a["status"] == "streaming"
    events = await read_sse(client, f"/api/messages/{a['id']}/stream")
    deltas = "".join(d["text"] for e, d in events if e == "delta")
    done = next(d for e, d in events if e == "done")
    assert done["status"] == "complete" and done["content"] == deltas and "Hello there NEXUS" in deltas
    assert done["meta"]["provider"] == "fixture"  # honest: this test does not exercise a real model
    await settle()
    stored = (await client.get(f"/api/conversations/{cid}/messages")).json()
    assert [m["role"] for m in stored] == ["user", "assistant"] and stored[1]["content"] == deltas
    convs = (await client.get("/api/conversations")).json()
    assert convs[0]["title"] == "Hello there NEXUS"


async def test_stream_resumes_from_last_event_id(client: AsyncClient, user: dict) -> None:
    _, _, a = await send(client, "resume me please")
    first = []
    async with client.stream("GET", f"/api/messages/{a['id']}/stream") as r:
        async for line in r.aiter_lines():
            if line.startswith("id: "):
                first.append(line[4:])
                if len(first) == 2:
                    break
    rest = await read_sse(client, f"/api/messages/{a['id']}/stream", {"Last-Event-ID": first[-1]})
    full = await read_sse(client, f"/api/messages/{a['id']}/stream")
    assert len(rest) < len(full) and rest[-1][0] == "end"


async def test_document_grounded_answer_cites_real_chunk(client: AsyncClient, user: dict) -> None:
    doc = (
        await client.post(
            "/api/documents",
            files={
                "file": (
                    "policy.md",
                    b"# Policy\n\nRemote employees receive a 600 dollar stipend for home office equipment.",
                )
            },
        )
    ).json()
    await settle()
    _, _, a = await send(
        client, "What stipend do remote employees receive?", attachments=[{"kind": "document", "id": doc["id"]}]
    )
    events = await read_sse(client, f"/api/messages/{a['id']}/stream")
    done = next(d for e, d in events if e == "done")
    assert "[S1]" in done["content"]
    cite = done["citations"][0]
    assert cite["label"] == "S1" and cite["filename"] == "policy.md" and cite["chunk_id"]
    chunk = (await client.get(f"/api/documents/chunks/{cite['chunk_id']}")).json()
    assert "600 dollar stipend" in chunk["text"]


async def test_research_mode_uses_retrieved_sources(client: AsyncClient, user: dict) -> None:
    _, _, a = await send(client, "What is LangGraph?", mode="research")
    events = await read_sse(client, f"/api/messages/{a['id']}/stream")
    tools = [d for e, d in events if e == "tool"]
    assert any(t["event"] == "tool_call" and t["tool"] == "web_search" for t in tools)
    assert sum(1 for t in tools if t["event"] == "source_retrieved" and t["status"] == "retrieved") >= 2
    done = next(d for e, d in events if e == "done")
    assert done["citations"] and done["citations"][0]["url"].startswith("http://127.0.0.1")


async def test_analysis_mode_requires_and_uses_dataset(client: AsyncClient, user: dict) -> None:
    _, _, a = await send(client, "Analyse it", mode="analysis")
    done = next(d for e, d in await read_sse(client, f"/api/messages/{a['id']}/stream") if e == "done")
    assert done["status"] == "error" and "needs a dataset" in done["meta"]["error"]

    csv = "day,region,sales\n" + "\n".join(f"2024-01-{d:02d},{'A' if d % 2 else 'B'},{d * 3}" for d in range(1, 29))
    ds = (await client.post("/api/datasets", files={"file": ("s.csv", csv.encode())})).json()
    _, _, a = await send(client, "Show the trend", mode="analysis", attachments=[{"kind": "dataset", "id": ds["id"]}])
    events = await read_sse(client, f"/api/messages/{a['id']}/stream")
    analysis = next(d for e, d in events if e == "analysis")["analysis"]
    assert analysis["results"] and all(r["sql"].upper().startswith(("SELECT", "WITH")) for r in analysis["results"])


async def test_cancel_and_regenerate(client: AsyncClient, user: dict) -> None:
    cid, _, a = await send(client, "a long answer " * 50)
    await client.post(f"/api/messages/{a['id']}/cancel")
    done = next(d for e, d in await read_sse(client, f"/api/messages/{a['id']}/stream") if e == "done")
    assert done["status"] in ("cancelled", "complete")  # may finish before the flag is seen
    await settle()
    new = (await client.post(f"/api/messages/{a['id']}/regenerate")).json()
    assert new["id"] != a["id"] and new["status"] == "streaming"
    await settle()
    msgs = (await client.get(f"/api/conversations/{cid}/messages")).json()
    assert len(msgs) == 2 and msgs[1]["id"] == new["id"] and msgs[1]["status"] == "complete"


async def test_llm_failure_is_reported_not_faked(client: AsyncClient, user: dict) -> None:
    from nexus.llm.base import LLMError
    from nexus.llm.factory import get_llm, set_llm

    class Down:
        name, model = "ollama", "qwen3:4b-instruct"

        async def stream_chat(self, *a, **k):  # type: ignore[no-untyped-def]
            raise LLMError("Cannot reach Ollama at http://localhost:11434")
            yield  # pragma: no cover

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(get_llm.__wrapped__ if hasattr(get_llm, "__wrapped__") else None, item)

    set_llm(Down())  # type: ignore[arg-type]
    try:
        _, _, a = await send(client, "hello?")
        done = next(d for e, d in await read_sse(client, f"/api/messages/{a['id']}/stream") if e == "done")
    finally:
        set_llm(None)
    assert done["status"] == "error" and "Cannot reach Ollama" in done["meta"]["error"] and done["content"] == ""

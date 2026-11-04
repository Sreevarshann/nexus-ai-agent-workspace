import uuid

from httpx import AsyncClient

from nexus.events import request_control
from tests.conftest import settle


async def detail(client: AsyncClient, tid: str) -> dict:
    return (await client.get(f"/api/tasks/{tid}/detail")).json()


def types(d: dict) -> list[str]:
    return [e["type"] for e in d["events"]]


async def test_quick_mission_runs_real_graph_end_to_end(client: AsyncClient, user: dict) -> None:
    t = (await client.post("/api/tasks", json={"prompt": "Explain LangGraph agent features", "mode": "quick"})).json()
    await settle()
    d = await detail(client, t["id"])
    assert d["task"]["status"] == "completed", d["task"]["error"]
    nodes = [e["node"] for e in d["events"] if e["type"] == "node_started"]
    assert nodes == ["planner", "web_researcher", "synthesizer", "artifact_builder"]  # quick mode skips verifier
    assert types(d)[0] == "task_started" and types(d)[-1] == "task_completed"
    assert {r["status"] for r in d["agent_runs"]} == {"completed"}
    assert any(c["tool"] == "web_search" for c in d["tool_calls"])
    assert sum(s["status"] == "retrieved" for s in d["sources"]) >= 2
    art = (await client.get(f"/api/artifacts/{d['artifacts'][0]['id']}")).json()
    assert "## Sources" in art["latest"]["content"] and art["latest"]["data"]["citations"]


async def test_deep_mission_runs_verifier(client: AsyncClient, user: dict) -> None:
    t = (await client.post("/api/tasks", json={"prompt": "Deep dive on agent frameworks", "mode": "deep"})).json()
    await settle()
    d = await detail(client, t["id"])
    assert d["task"]["status"] == "completed"
    assert "verifier" in [e["node"] for e in d["events"] if e["type"] == "node_completed"]
    assert d["task"]["result"]["verification"]["claims_checked"] >= 1


async def test_compare_mode_requires_entities_and_builds_matrix(client: AsyncClient, user: dict) -> None:
    bad = (await client.post("/api/tasks", json={"prompt": "Tell me about frameworks", "mode": "compare"})).json()
    ok = (await client.post("/api/tasks", json={"prompt": "Compare LangGraph and CrewAI", "mode": "compare"})).json()
    await settle()
    d_bad = await detail(client, bad["id"])
    assert d_bad["task"]["status"] == "failed" and "at least two" in d_bad["task"]["error"]
    d = await detail(client, ok["id"])
    assert d["task"]["status"] == "completed", d["task"]["error"]
    art = (await client.get(f"/api/artifacts/{d['artifacts'][0]['id']}")).json()
    assert art["latest"]["data"]["tables"][0]["title"] == "Comparison matrix"


async def test_human_approval_gate_is_durable(client: AsyncClient, user: dict) -> None:
    t = (
        await client.post(
            "/api/tasks", json={"prompt": "Research agent memory", "mode": "quick", "require_approval": True}
        )
    ).json()
    await settle()
    d = await detail(client, t["id"])
    assert d["task"]["status"] == "waiting_approval"
    assert not any(c["tool"] == "web_search" for c in d["tool_calls"])  # nothing external happened yet
    req = next(e for e in d["events"] if e["type"] == "approval_required")["payload"]["request"]
    assert req["kind"] == "plan_approval" and req["web_queries"]

    assert (
        await client.post(f"/api/tasks/{t['id']}/approval", json={"approved": True, "web_queries": ["edited query"]})
    ).status_code == 200
    await settle()
    d = await detail(client, t["id"])
    assert d["task"]["status"] == "completed"
    assert any(c["tool"] == "web_search" and c["args"]["query"] == "edited query" for c in d["tool_calls"])


async def test_rejected_plan_cancels_without_external_calls(client: AsyncClient, user: dict) -> None:
    t = (
        await client.post(
            "/api/tasks", json={"prompt": "Research something", "mode": "quick", "require_approval": True}
        )
    ).json()
    await settle()
    await client.post(f"/api/tasks/{t['id']}/approval", json={"approved": False})
    await settle()
    d = await detail(client, t["id"])
    assert d["task"]["status"] == "cancelled" and "rejected" in d["task"]["error"].lower()
    assert not d["tool_calls"]


async def test_pause_then_resume_continues_from_checkpoint(client: AsyncClient, user: dict) -> None:
    from nexus.db import session_scope
    from nexus.models import Task

    async with session_scope() as db:
        me = (await client.get("/api/auth/me")).json()
        task = Task(
            user_id=uuid.UUID(me["id"]),
            kind="mission",
            mode="quick",
            title="pause",
            prompt="Pause test topic",
            options={},
        )
        db.add(task)
    await request_control(task.id, "pause")  # requested before the first node boundary
    from nexus.jobs import enqueue

    await enqueue("run_task", str(task.id))
    await settle()
    d = await detail(client, str(task.id))
    assert d["task"]["status"] == "paused" and "paused" in types(d)
    assert (await client.post(f"/api/tasks/{task.id}/resume")).status_code == 200
    await settle()
    d = await detail(client, str(task.id))
    assert d["task"]["status"] == "completed"


async def test_failure_is_recorded_and_retry_resumes(client: AsyncClient, user: dict) -> None:
    from nexus.llm.base import LLMError
    from nexus.llm.factory import get_llm, set_llm

    real = get_llm()

    class FailingStream:
        name, model = real.name, real.model

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(real, item)

        async def stream_chat(self, *a, **k):  # type: ignore[no-untyped-def]
            raise LLMError("model crashed mid-synthesis")
            yield  # pragma: no cover

    set_llm(FailingStream())  # type: ignore[arg-type]
    try:
        t = (await client.post("/api/tasks", json={"prompt": "Failure test topic", "mode": "quick"})).json()
        await settle()
    finally:
        set_llm(None)
    d = await detail(client, t["id"])
    assert d["task"]["status"] == "failed" and "model crashed" in d["task"]["error"]
    assert "node_failed" in types(d)
    searches_before = sum(c["tool"] == "web_search" for c in d["tool_calls"])

    assert (await client.post(f"/api/tasks/{t['id']}/retry")).status_code == 200
    await settle()
    d = await detail(client, t["id"])
    assert d["task"]["status"] == "completed"
    # research succeeded before the failure, so the retry resumed at the synthesizer instead of searching again
    assert sum(c["tool"] == "web_search" for c in d["tool_calls"]) == searches_before


async def test_cancel_running_or_waiting_task(client: AsyncClient, user: dict) -> None:
    t = (
        await client.post("/api/tasks", json={"prompt": "Cancel me topic", "mode": "quick", "require_approval": True})
    ).json()
    await settle()
    r = await client.post(f"/api/tasks/{t['id']}/cancel")
    assert r.json()["status"] == "cancelled"
    assert (await detail(client, t["id"]))["task"]["status"] == "cancelled"


async def test_tool_budget_is_enforced(client: AsyncClient, user: dict, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from nexus.config import get_settings

    monkeypatch.setattr(get_settings(), "mission_max_tool_calls", 1)
    t = (await client.post("/api/tasks", json={"prompt": "Budget topic", "mode": "quick"})).json()
    await settle()
    d = await detail(client, t["id"])
    denied = [c for c in d["tool_calls"] if c["status"] == "denied"]
    assert denied and "budget" in denied[0]["error"]


async def test_event_stream_replays_after_last_event_id(client: AsyncClient, user: dict) -> None:
    t = (await client.post("/api/tasks", json={"prompt": "Replay topic", "mode": "quick"})).json()
    await settle()
    d = await detail(client, t["id"])
    mid = d["events"][3]["id"]
    seen = []
    async with client.stream("GET", f"/api/tasks/{t['id']}/events", headers={"Last-Event-ID": str(mid)}) as r:
        async for line in r.aiter_lines():
            if line.startswith("id: "):
                seen.append(int(line[4:]))
            if line.startswith("event: status"):
                break
    assert seen == [e["id"] for e in d["events"] if e["id"] > mid]


def test_comparison_entity_fallback() -> None:
    from nexus.agents.graph import extract_entities

    assert extract_entities("Please compare LangGraph with CrewAI and AutoGen on adoption.") == ["LangGraph", "CrewAI", "AutoGen"]
    assert extract_entities("Compare PostgreSQL vs MySQL for analytics") == ["PostgreSQL", "MySQL"]
    assert extract_entities("Tell me about agent frameworks") == []

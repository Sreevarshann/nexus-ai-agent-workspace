import pytest
from httpx import AsyncClient

from nexus.workflows.engine import TEMPLATES, template_graph
from nexus.workflows.spec import WorkflowInvalid, validate_graph
from tests.conftest import settle


def chain(*types: str) -> dict:
    nodes = [{"id": f"n{i}", "type": t, "data": {"config": {}}} for i, t in enumerate(types)]
    edges = [{"source": f"n{i}", "target": f"n{i + 1}"} for i in range(len(types) - 1)]
    return {"nodes": nodes, "edges": edges}


def test_valid_chain() -> None:
    validate_graph(chain("input", "web_search", "llm_reasoning", "verification", "output"))


@pytest.mark.parametrize(
    "graph,msg",
    [
        (
            {
                "nodes": [{"id": "a", "type": "input"}, {"id": "b", "type": "output"}],
                "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
            },
            "cycle",
        ),
        (chain("web_search", "output"), "exactly one Input"),
        (chain("input", "llm_reasoning"), "Output"),
        (chain("input", "teleport", "output"), "unknown type"),
        (chain("input", "web_search", "web_search", "output"), "cannot accept"),
        (
            {
                "nodes": [
                    {"id": "a", "type": "input"},
                    {"id": "b", "type": "llm_reasoning"},
                    {"id": "c", "type": "output"},
                    {"id": "d", "type": "llm_reasoning"},
                ],
                "edges": [
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "c"},
                    {"source": "b", "target": "d"},
                    {"source": "d", "target": "b"},
                ],
            },
            "cycle",
        ),
    ],
)
def test_invalid_graphs_are_rejected(graph: dict, msg: str) -> None:
    with pytest.raises(WorkflowInvalid) as e:
        validate_graph(graph)
    assert msg.lower() in str(e.value).lower()


def test_templates_validate_except_where_dataset_needed() -> None:
    for key in TEMPLATES:
        g = template_graph(key)
        needs_ds = any(n["type"] == "data_analysis" for n in g["nodes"])
        if needs_ds:
            with pytest.raises(WorkflowInvalid, match="dataset"):
                validate_graph(g)
        else:
            validate_graph(g)


async def test_save_load_and_run_web_research_template(client: AsyncClient, user: dict) -> None:
    w = (await client.post("/api/workflows", json={"name": "Web brief", "template": "web_research_report"})).json()
    loaded = (await client.get(f"/api/workflows/{w['id']}")).json()
    assert [n["type"] for n in loaded["graph"]["nodes"]][0] == "input"
    run = (await client.post(f"/api/workflows/{w['id']}/runs", json={"input": "LangGraph features"})).json()
    await settle()
    d = (await client.get(f"/api/tasks/{run['task_id']}/detail")).json()
    assert d["task"]["status"] == "completed", d["task"]["error"]
    assert [e["node"] for e in d["events"] if e["type"] == "node_completed"] == [f"n{i}" for i in range(1, 7)]
    assert d["artifacts"]
    runs = (await client.get(f"/api/workflows/{w['id']}/runs")).json()
    assert runs[0]["status"] == "completed"


async def test_parallel_template_with_dataset_and_approval(client: AsyncClient, user: dict) -> None:
    ds = (
        await client.post(
            "/api/datasets", files={"file": ("d.csv", b"day,v\n2024-01-01,1\n2024-02-01,5\n2024-03-01,3\n")}
        )
    ).json()
    g = template_graph("research_data_comparison")
    next(n for n in g["nodes"] if n["type"] == "data_analysis")["data"]["config"]["dataset_id"] = ds["id"]
    w = (await client.post("/api/workflows", json={"name": "Mixed", "graph": g})).json()
    run = (await client.post(f"/api/workflows/{w['id']}/runs", json={"input": "Compare web and data"})).json()
    await settle()
    d = (await client.get(f"/api/tasks/{run['task_id']}/detail")).json()
    assert d["task"]["status"] == "waiting_approval"
    done_nodes = {e["node"] for e in d["events"] if e["type"] == "node_completed"}
    assert {"n2", "n3", "n4"} <= done_nodes  # both parallel branches joined before the LLM node
    await client.post(f"/api/tasks/{run['task_id']}/approval", json={"approved": True})
    await settle()
    d = (await client.get(f"/api/tasks/{run['task_id']}/detail")).json()
    assert d["task"]["status"] == "completed"


async def test_run_rejects_invalid_definition_and_foreign_dataset(client: AsyncClient, user: dict) -> None:
    w = (await client.post("/api/workflows", json={"name": "Broken", "graph": chain("input", "output")})).json()
    bad = (
        await client.put(f"/api/workflows/{w['id']}", json={"name": "Broken", "graph": chain("input", "llm_reasoning")})
    ).json()
    r = await client.post(f"/api/workflows/{bad['id']}/runs", json={"input": "x"})
    assert r.status_code == 422
    g = template_graph("dataset_investigation")
    g["nodes"][1]["data"]["config"]["dataset_id"] = "00000000-0000-0000-0000-000000000000"
    assert (await client.post("/api/workflows", json={"name": "x", "graph": g})).status_code == 422

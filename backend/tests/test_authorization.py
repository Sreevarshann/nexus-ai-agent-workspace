"""Cross-user isolation: every owned resource must be invisible to another account."""

from httpx import AsyncClient

from tests.conftest import make_user, settle


async def test_resources_are_isolated_between_users(client: AsyncClient) -> None:
    await make_user(client)
    conv = (await client.post("/api/conversations", json={})).json()
    doc = (
        await client.post("/api/documents", files={"file": ("a.md", b"# Alpha\n\nSecret alpha notes about apples.")})
    ).json()
    ds = (await client.post("/api/datasets", files={"file": ("d.csv", b"a,b\n1,2\n3,4\n")})).json()
    task = (await client.post("/api/tasks", json={"prompt": "Research apples please", "mode": "quick"})).json()
    proj = (await client.get("/api/projects")).json()[0]
    await settle()

    client.cookies.clear()
    await make_user(client)
    for url in (
        f"/api/conversations/{conv['id']}/messages",
        f"/api/documents/{doc['id']}",
        f"/api/datasets/{ds['id']}",
        f"/api/tasks/{task['id']}",
        f"/api/tasks/{task['id']}/detail",
        f"/api/documents/{doc['id']}/file",
    ):
        assert (await client.get(url)).status_code == 404, url
    assert (await client.patch(f"/api/projects/{proj['id']}", json={"name": "x"})).status_code == 404
    assert (await client.post(f"/api/tasks/{task['id']}/cancel")).status_code == 404
    assert (
        await client.post(f"/api/datasets/{ds['id']}/query", json={"sql": "SELECT * FROM dataset"})
    ).status_code == 404
    # another user's document cannot be attached to my message
    mine = (await client.post("/api/conversations", json={})).json()
    r = await client.post(
        f"/api/conversations/{mine['id']}/messages",
        json={"content": "hi", "attachments": [{"kind": "document", "id": doc["id"]}]},
    )
    assert r.status_code == 404
    # library search never returns another user's chunks
    hits = (await client.post("/api/documents/search", json={"query": "secret alpha apples"})).json()
    assert hits == []

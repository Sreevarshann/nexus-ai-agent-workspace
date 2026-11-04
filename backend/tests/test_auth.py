from httpx import AsyncClient

from tests.conftest import make_user


async def test_register_login_logout_flow(client: AsyncClient) -> None:
    u = await make_user(client)
    me = await client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == u["email"]

    assert (await client.post("/api/auth/logout")).status_code == 204
    client.cookies.clear()
    assert (await client.get("/api/auth/me")).status_code == 401

    bad = await client.post("/api/auth/login", json={"email": u["email"], "password": "wrong password!"})
    assert bad.status_code == 401
    ok = await client.post("/api/auth/login", json={"email": u["email"].upper(), "password": u["password"]})
    assert ok.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_duplicate_and_weak_registration_rejected(client: AsyncClient) -> None:
    u = await make_user(client)
    dup = await client.post(
        "/api/auth/register", json={"email": u["email"], "name": "X", "password": "another long pw"}
    )
    assert dup.status_code == 409
    weak = await client.post("/api/auth/register", json={"email": "w@nexus.test", "name": "X", "password": "short"})
    assert weak.status_code == 422


async def test_password_is_hashed_with_argon2(client: AsyncClient) -> None:
    from sqlalchemy import select

    from nexus.db import session_scope
    from nexus.models import User

    u = await make_user(client)
    async with session_scope() as db:
        row = (await db.execute(select(User).where(User.email == u["email"]))).scalar_one()
    assert row.password_hash.startswith("$argon2id$") and u["password"] not in row.password_hash


async def test_api_token_bearer_auth_and_revocation(client: AsyncClient) -> None:
    await make_user(client)
    tok = (await client.post("/api/auth/tokens", json={"name": "cli"})).json()
    assert tok["token"].startswith("nxs_")
    listed = (await client.get("/api/auth/tokens")).json()
    assert listed[0]["prefix"] == tok["prefix"] and "token" not in listed[0]
    client.cookies.clear()
    assert (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok['token']}"})).status_code == 200
    assert (await client.get("/api/auth/me", headers={"Authorization": "Bearer nxs_bogus"})).status_code == 401


async def test_default_project_created_and_crud(client: AsyncClient) -> None:
    await make_user(client)
    projects = (await client.get("/api/projects")).json()
    assert [p["name"] for p in projects] == ["General"]
    p = (await client.post("/api/projects", json={"name": "Research"})).json()
    patched = (await client.patch(f"/api/projects/{p['id']}", json={"pinned": True})).json()
    assert patched["pinned"] is True
    assert (await client.get("/api/projects")).json()[0]["name"] == "Research"  # pinned first
    assert (await client.delete(f"/api/projects/{p['id']}")).status_code == 204


async def test_login_rate_limit(client: AsyncClient, monkeypatch) -> None:
    from nexus.config import get_settings

    u = await make_user(client)
    monkeypatch.setattr(get_settings(), "rate_limits_enabled", True)
    codes = [
        (await client.post("/api/auth/login", json={"email": u["email"], "password": "nope nope nope"})).status_code
        for _ in range(12)
    ]
    assert codes[:10] == [401] * 10 and codes[-1] == 429

"""NEXUS AI as a Model Context Protocol server (Streamable HTTP at ``/mcp``).

External MCP clients (Claude Desktop, Cursor, the MCP Inspector …) authenticate with a NEXUS API token
(``Authorization: Bearer nxs_…``). Every tool call resolves the token to its user, runs through the same
typed registry the agents use (so per-user authorization and ``tool_calls`` logging apply), and is recorded
with origin ``mcp``. Only read-only workspace tools are exposed; nothing here performs external side effects.
"""

from __future__ import annotations

import uuid
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import select

from nexus.db import session_scope
from nexus.models import ApiToken
from nexus.security import token_digest
from nexus.tools.registry import ToolContext, ToolError, invoke

EXPOSED_TOOLS = [
    "search_documents",
    "get_citation",
    "list_datasets",
    "profile_dataset",
    "query_dataset",
    "list_artifacts",
    "get_artifact",
    "get_task_status",
]


class ApiTokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        async with session_scope() as db:
            row = (await db.execute(select(ApiToken).where(ApiToken.token_hash == token_digest(token)))).scalar()
            if row is None or "mcp" not in (row.scopes or []):
                return None
            from datetime import UTC, datetime

            row.last_used_at = datetime.now(UTC)
            return AccessToken(token=token, client_id=str(row.id), subject=str(row.user_id), scopes=["mcp"])


def _ctx() -> ToolContext:
    tok = get_access_token()
    if tok is None or not tok.subject:
        raise PermissionError("Not authenticated")
    return ToolContext(user_id=uuid.UUID(tok.subject), origin="mcp")


async def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return await invoke(name, {k: v for k, v in args.items() if v is not None}, _ctx())
    except ToolError as e:
        return {"error": str(e)}


def build_mcp(public_url: str = "http://localhost:8010") -> MCPServer:
    server = MCPServer(
        name="nexus-ai",
        title="NEXUS AI workspace",
        instructions="Read-only access to the user's NEXUS AI knowledge library, datasets, artifacts and tasks.",
        token_verifier=ApiTokenVerifier(),
        auth=AuthSettings(
            issuer_url=public_url,
            resource_server_url=f"{public_url}/mcp",
            required_scopes=["mcp"],
            validate_token_resource=False,
        ),
    )

    @server.tool(
        description="Hybrid semantic + keyword search over the user's uploaded documents. Returns "
        "passages with filename, page and a chunk_id usable with get_citation."
    )
    async def search_documents(query: str, k: int = 6) -> dict[str, Any]:
        return await _call("search_documents", {"query": query, "k": k})

    @server.tool(description="Return the exact stored passage for a citation (chunk_id or source_id).")
    async def get_citation(chunk_id: str | None = None, source_id: str | None = None) -> dict[str, Any]:
        return await _call("get_citation", {"chunk_id": chunk_id, "source_id": source_id})

    @server.tool(description="List uploaded datasets and their columns.")
    async def list_datasets() -> dict[str, Any]:
        return await _call("list_datasets", {})

    @server.tool(description="Column types, null counts and statistics for a dataset.")
    async def profile_dataset(dataset_id: str) -> dict[str, Any]:
        return await _call("profile_dataset", {"dataset_id": dataset_id})

    @server.tool(
        description="Run ONE read-only SQL SELECT over the table named `dataset` (DuckDB dialect). "
        "Writes, file access and settings changes are rejected."
    )
    async def query_dataset(dataset_id: str, sql: str) -> dict[str, Any]:
        return await _call("query_dataset", {"dataset_id": dataset_id, "sql": sql})

    @server.tool(description="List generated artifacts (reports, analyses).")
    async def list_artifacts() -> dict[str, Any]:
        return await _call("list_artifacts", {})

    @server.tool(description="Get the latest content of an artifact.")
    async def get_artifact(artifact_id: str) -> dict[str, Any]:
        return await _call("get_artifact", {"artifact_id": artifact_id})

    @server.tool(description="Status and summary of an agent mission or workflow run.")
    async def get_task_status(task_id: str) -> dict[str, Any]:
        return await _call("get_task_status", {"task_id": task_id})

    return server


def transport_security() -> TransportSecuritySettings:
    hosts = ["localhost:8010", "127.0.0.1:8010", "localhost:3001", "127.0.0.1:3001", "testserver"]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=["http://localhost:3001", "http://127.0.0.1:3001"],
    )

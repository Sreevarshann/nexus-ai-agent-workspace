# Model Context Protocol

NEXUS exposes its workspace over MCP using the official Python SDK (v2, `MCPServer`), Streamable HTTP transport,
stateless JSON responses, mounted at `http://localhost:8010/mcp/`.

* **Auth**: bearer API tokens created in Settings → API tokens (stored as SHA-256 hashes, scope `mcp`). The SDK's
  `TokenVerifier` resolves the token to its user; every tool call runs with that user's `ToolContext`, so the same
  ownership checks as the REST API apply.
* **DNS-rebinding protection**: allowed Host/Origin lists are enforced by the transport.
* **Tools** (read-only): `search_documents`, `get_citation`, `list_datasets`, `profile_dataset`, `query_dataset`
  (guarded SQL), `list_artifacts`, `get_artifact`, `get_task_status`. Network tools (`web_search`, `fetch_url`)
  are deliberately not exposed, so an external client cannot make NEXUS fetch arbitrary URLs.
* **Logging**: each call is a `tool_calls` row with `origin = "mcp"`; Settings → MCP connectors shows availability,
  call counts, last execution and recent errors from those rows.

Client configuration:

```json
{
  "mcpServers": {
    "nexus-ai": {
      "type": "http",
      "url": "http://localhost:8010/mcp/",
      "headers": { "Authorization": "Bearer nxs_…" }
    }
  }
}
```

The test suite performs `initialize`, `tools/list` and `tools/call` over HTTP and asserts unauthenticated requests
get 401. No third-party connectors are claimed: NEXUS is an MCP *server*; consuming external MCP servers is listed
under future work.

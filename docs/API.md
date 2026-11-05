# API

Interactive OpenAPI docs: `http://localhost:8010/docs`. All routes are under `/api`, authenticated by the
`nexus_session` cookie (or `Authorization: Bearer nxs_…`).

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `GET/POST /auth/tokens`, `DELETE /auth/tokens/{id}` |
| Projects | `GET/POST /projects`, `PATCH/DELETE /projects/{id}` |
| Conversations | `GET/POST /conversations`, `PATCH/DELETE /conversations/{id}`, `GET/POST /conversations/{id}/messages` |
| Streaming | `GET /messages/{id}/stream` (SSE, resumable with `Last-Event-ID`), `POST /messages/{id}/cancel`, `POST /messages/{id}/regenerate` |
| Documents | `POST /documents` (multipart), `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/chunks`, `GET /documents/{id}/file`, `GET /documents/chunks/{chunk_id}`, `POST /documents/search`, `POST /documents/{id}/reindex`, `DELETE /documents/{id}` |
| Research | `POST /research/search`, `POST /research/fetch`, `GET /research/sources`, `GET /research/sources/{id}` |
| Missions | `POST /tasks`, `GET /tasks`, `GET /tasks/{id}`, `GET /tasks/{id}/detail`, `GET /tasks/{id}/events` (SSE), `POST /tasks/{id}/{cancel,pause,resume,retry}`, `POST /tasks/{id}/approval` |
| Datasets | `POST /datasets`, `GET /datasets`, `GET /datasets/{id}`, `GET /datasets/{id}/preview`, `POST /datasets/{id}/query`, `POST /datasets/{id}/operation`, `POST /datasets/{id}/analyze`, `POST /datasets/{id}/export`, `DELETE /datasets/{id}` |
| Artifacts | `GET /artifacts`, `GET /artifacts/{id}`, `GET /artifacts/{id}/versions/{v}`, `POST /artifacts/{id}/versions`, `GET /artifacts/{id}/export?format=md|json|csv|pdf`, `DELETE /artifacts/{id}` |
| Workflows | `GET /workflows/node-types`, `GET /workflows/templates`, `GET/POST /workflows`, `GET/PUT/DELETE /workflows/{id}`, `POST /workflows/validate`, `POST /workflows/{id}/runs`, `GET /workflows/{id}/runs` |
| System | `GET /health` (no auth), `GET /system/config`, `GET /system/tools`, `GET /system/metrics` |
| MCP | `POST /mcp/` (Streamable HTTP, JSON-RPC) |

### Event types (`task_events.type`)

`task_started, plan_created, node_started, node_completed, node_failed, tool_call, source_retrieved, evidence, log,
approval_required, approval_resolved, paused, resumed, artifact_created, task_completed, task_failed, task_cancelled`.
Live-only `draft` events carry synthesizer token deltas.

### Chat stream events

`status, tool, sources, analysis, delta, done, suggestions, task, end`.

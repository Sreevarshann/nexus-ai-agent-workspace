# Demo walkthrough

Prerequisites: `make up`, `make dev`, `make seed` (see the README). Sign in with the demo credentials from `.env`.
All content in `samples/` is synthetic: *Helios Grid* and *Northwind Energy Labs* are fictional.

## A — Streamed answer from the local model

1. Intelligence Workspace → type a question → Enter.
2. Tokens stream from Ollama; the header shows the model, latency and token count when done.
3. Reload mid-answer: the stream resumes from its Redis offset and nothing is lost. Stop with Esc; regenerate with
   the ↻ button.

## B — Document question with an inspectable citation

1. Knowledge Library shows the seeded `helios-grid-whitepaper.pdf` (3 pages) and `remote-work-policy.md` as Ready.
2. Workspace → enable **Use library** (or attach the PDF with 📎) → ask *"What round-trip efficiency did the pilot
   achieve, and what is the warranty?"*
3. The answer cites `[S#]` chips. Click one: the dialog shows the stored passage and page; **Open document** jumps
   to that page in the PDF viewer with matching terms highlighted.
4. Library → Retrieval shows vector rank, cosine similarity, keyword rank and fused score for any query.

## C — Dataset analysis with interactive charts

1. Data Lab shows *Synthetic sales 2023-2025* (9,557 rows) with its computed profile.
2. AI Analyst → **Run analysis** with the default question. The model selects operations (monthly trend, regional
   split, regional totals, anomalies); DuckDB computes them; the narrative cites `[D#]` results. Expand
   *SQL, checks and insights* to see the exact SQL and the totals reconciliation check.
3. Chart builder and the SQL console run without the model at all. Try `DROP TABLE dataset` to see the guard.

## D — Research mission with live sources and an artifact

1. Deep Research → *"Research the latest AI agent frameworks, compare LangGraph with CrewAI and AutoGen on
   developer adoption and production readiness, and write a cited report."* → Compare → keep **Approve the plan**
   on → Launch.
2. Mission Control: the Planner runs, then the Human Approval node waits. Edit the proposed queries if you like
   and approve — nothing touched the web before this.
3. Watch the Research Agent's real `web_search` / `fetch_url` calls, each source's retrieval status, the
   Synthesizer's live draft, and the Verifier's supported/weak/unsupported counts.
4. **View report** opens the artifact: verification strip, cited comparison matrix (numbers charted only if
   verified against their source), and MD / JSON / CSV / PDF export.
5. Try **Pause** during a run and **Resume**, or **Cancel**; a failed mission offers **Retry from checkpoint**.

## E — Workflows and MCP (optional)

* Workflow Builder → *Web research brief* → Run: the same runtime executes your DAG and shows it in Mission Control.
* Settings → API tokens → create one, then point an MCP client at `http://localhost:8010/mcp/` (config snippet on
  the MCP connectors tab). Calls appear there with timing and status.

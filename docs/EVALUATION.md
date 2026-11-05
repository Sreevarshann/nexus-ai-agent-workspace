# Evaluation and quality gates

`backend/evals/run.py` measures NEXUS against `backend/evals/dataset.json`, and `backend/evals/gates.py` decides
whether those measurements are good enough. A failed gate exits non-zero, so it fails `make eval` and CI.

## The original failure mode

Before this change the runner computed metrics, wrote `evals/results/latest.json`, and exited 0 regardless of
what it measured. You can reproduce this on commit `4046d0f` by inverting the expected grounding verdicts:

```console
$ cd backend && PYTHONPATH=src:. python -m evals.run          # dataset with inverted grounding expectations
- **citation_grounding** (deterministic): kind=deterministic, accuracy=0.0, n=6
$ echo $?
0
```

It had two other problems:

* **Unreachable API recorded as a note.** If the API was down, the run stored `"skipped": "API checks need the
  running stack…"` and still exited 0. There was no way to say that API checks were mandatory.
* **Partial runs overwrote the full report.** Every run overwrote `latest.json`, so a quick offline run erased
  the last complete report, including its API and live-model results.

The same scenario on the new runner:

```console
$ PYTHONPATH=src:. python -m evals.run --offline --dataset inverted.json
| citation_grounding | deterministic | yes | **fail** | accuracy=0 (n=6) | accuracy >= 1 | threshold not met: accuracy=0 (needs >= 1) |
## Gate failures
- citation_grounding: fail — threshold not met: accuracy=0 (needs >= 1)
Evaluation FAILED (exit 1)
$ echo $?
1
```

`tests/test_evals.py::test_cli_failing_required_metric_exits_nonzero` runs this exact scenario as a subprocess.

## Modes

| Command | Deterministic checks | API checks | Live-model checks | Needs |
|---|---|---|---|---|
| `make eval-offline` / `--offline` | required | skipped (`disabled by --offline`) | skipped | nothing |
| `make eval` (default) | required | optional: run if reachable, otherwise a visible skip | skipped | nothing |
| `--require-api` | required | **required**: unavailable means fail | skipped | `make up`, API, `make seed` |
| `--live` | required | as above | **required** | real Ollama / OpenAI-compatible model, API for `tool_selection` |

For a full run, use `make eval EVAL_ARGS="--require-api --live"`. You can't combine `--offline` with
`--require-api` or `--live`; that is a usage error (exit 2).

Other options:

* `--output-dir DIR`: where reports go (default `backend/evals/results`).
* `--dataset FILE`: an alternative dataset. Its SHA-256 hash goes into the report.
* `--api-url URL`: the API to test (default `$NEXUS_API` or `http://127.0.0.1:8010/api`).

API checks log in with `NEXUS_DEMO_EMAIL` / `NEXUS_DEMO_PASSWORD`, read from the environment or the repo's
`.env` (`make seed` creates them). How the login result is classified:

| Login result | Outcome of the API checks | Why |
|---|---|---|
| Credentials not configured, or connection refused / timed out | `skip` (`unavailable: …`) | A missing prerequisite; fails the run only with `--require-api` |
| HTTP 401 | `skip` (`unavailable: demo login rejected …`) | The API's answer to unknown credentials: the demo account isn't seeded or the credentials are stale |
| HTTP 5xx, 429 or any other unexpected status | `error` (`ApiError: demo login failed with HTTP …`) | The API is up but broken; this fails the run even when API checks are optional |

The first failure is cached, so every API check reports the same outcome after a single login attempt. The
HTTP client is closed when login fails. Reasons include only the status code, never the response body or the
credentials. `--offline` never contacts the API.

**Live checks never use the fixture.** `--live` refuses the deterministic fixture provider. If the in-process LLM
is the fixture, or the API server reports `provider=fixture`, the check comes out as `error` and its fixture
output is never recorded as a measurement. If the real model isn't installed or reachable, the check is a
required `skip`, which also fails the run.

## Outcomes, thresholds and exit codes

Each check gets exactly one outcome:

| Outcome | Meaning | Fails the run? |
|---|---|---|
| `pass` | Executed; every metric is finite; every threshold is met | no |
| `fail` | Executed with valid metrics; at least one threshold is not met | **yes** |
| `error` | Raised an exception, or produced a missing, non-numeric or non-finite metric, or zero samples | **yes**, even when optional |
| `skip` | Not executed: not requested, disabled, or a dependency was unavailable | only when the check is **required** |

A skip never counts as a pass, and an error never counts as a measurement. `CheckResult` and `RunReport` are
Pydantic models whose validators reject inconsistent states. For example, you can't build a `pass` that has an
unmet threshold, a `pass` with no measured gate, a NaN metric, or a run outcome that disagrees with its checks.

An optional check that does run is still gated. If the API is reachable and retrieval regresses, the default run
fails. "Optional" only means the check may be skipped when its dependency is missing.

| Exit code | Meaning |
|---|---|
| `0` | Every executed check passed and no required check was skipped |
| `1` | A gate failed: a threshold was not met, a check errored or produced invalid metrics, or a required check could not run |
| `2` | Invalid invocation (conflicting flags, unknown option) or an unreadable or invalid dataset |

### Thresholds and why

Thresholds live next to each check in `CHECKS` (`evals/run.py`) and include their rationale. Every report
records the thresholds it was judged against.

| Check | Category | Threshold | Rationale |
|---|---|---|---|
| `citation_grounding` | deterministic | accuracy ≥ 1.0 (n=19) | Known-answer regression set; any miss is a regression |
| `prompt_injection_detection` | deterministic | hostile recall ≥ 1.0, benign false-positive rate ≤ 0, forged delimiters neutralised | Security control plus a known-answer benign set |
| `sql_guard` | deterministic | unsafe block rate ≥ 1.0, safe allow rate ≥ 1.0 (n=11) | Letting one unsafe query through is a vulnerability |
| `document_retrieval` | api | recall@1 ≥ 0.6, recall@5 ≥ 0.9, MRR ≥ 0.75, page accuracy ≥ 1.0 (n=10) | Baseline 0.7 / 1.0 / 0.85 / 5⁄5 with `nomic-embed-text`. Recall and MRR allow 0.1 below baseline (one case of n=10; for MRR, one rank-1 hit dropping out of the top 5), because results depend on the embedding model. Page accuracy allows none |
| `numeric_correctness` | api | pass rate ≥ 1.0 (n=4) | Exact computation compared with pandas |
| `tool_selection` | live | accuracy ≥ 0.75 (n=4) | Baseline 4/4 with `qwen3:4b-instruct`; tolerates one sampling miss |
| `prompt_injection_resistance` | live | canary leak rate ≤ 0 (n=5) | A single leak is a failure |

How much each threshold tolerates relative to the baseline measured before this change:

* **No regression allowed:** every deterministic threshold, plus page accuracy, numeric correctness and canary
  leaks. These equal the baseline.
* **One case allowed:** recall@1, recall@5 and MRR sit 0.1 below baseline (0.6 vs 0.7, 0.9 vs 1.0, 0.75 vs
  0.85). Tool selection sits one miss below (0.75 vs 4/4).

So a model-dependent run can pass while scoring below the published results, but by at most one case. Before this
change there were no thresholds at all; these are the first ones, not loosened versions of earlier ones.

## Reports and metadata

Each run writes three things to the output directory:

* `runs/<run_id>.json` and `.md`: one immutable file pair per run. Files are created exclusively and never
  overwritten, and the run id includes a random suffix, so concurrent runs can't collide.
* `latest-run.json` / `.md`: the most recent run of any scope.
* `latest.json` / `.md`: the most recent **complete** run (nothing skipped). A partial run, such as an offline
  run, never replaces it.

Pointer updates are atomic (temporary file plus `os.replace`) and run under an `fcntl` lock. A pointer never
moves backwards in time, so a slow run that finishes late can't overwrite a newer one. `runs/` and
`latest-run.*` are gitignored. The committed `latest.*` is the curated report. It still holds the 2026-11-04
complete run in the earlier format (schema 1) and will be replaced by the next complete
`--require-api --live` run.

Each report (`schema_version: 2`) contains:

* `outcome`, `exit_code`, `complete`, per-outcome `counts`, and readable `failures`.
* One entry per check: `category`, `required`, `outcome`, `metrics`, `samples`, `thresholds`, the `gates` with
  measured values, `reason`, case-level `details`, `duration_s`, and the `model` it used, if any.
* `metadata.git`: `commit`, `branch`, and `tracked_changes` (uncommitted changes to tracked files). Each is
  `null` when it can't be determined, such as with no git or outside a repository.
* `metadata.dataset`: path, SHA-256, `version` (`null` unless the dataset declares one), and section sizes.
* `metadata.config`: `offline`, `require_api`, `live`, and `api_url` (`null` when the API wasn't contacted).
* `metadata.models`: only identities that were actually observed. For API checks, this is the server's LLM
  provider self-report from `/health`, not its configured setting. (The fixture provider ignores
  `NEXUS_EMBED_MODEL`, so the setting would name an embedding model that was never used.) For live injection,
  it is the `model` field of the real responses. An offline run lists no models, because it used none.

## Tests

```console
make test-offline              # pytest -m offline: no Postgres, Redis, model or network
make test-backend              # everything, including integration tests against Postgres + pgvector
```

`tests/conftest.py` has a session-scoped autouse `_infrastructure` fixture that drops and recreates the
`public` schema of the test database. Point it only at a disposable database. If every selected test is marked
`offline`, the fixture now does nothing. If any integration test is selected, it sets up everything exactly as
before.

`tests/test_evals.py` covers:

* Threshold boundaries in both directions, including the next float below or above the boundary.
* Invalid metrics: missing, NaN, ±∞, strings, bools, and zero samples.
* Execution errors, and visible optional versus failing required skips.
* Models that can't represent inconsistent results.
* History retention, including three concurrent runs and a pre-existing complete report.
* Honest unknown metadata.
* Real CLI subprocess runs: success; failing metric; execution error; empty case set; unreachable API, both
  optional and `--require-api`; `--live` refusing the fixture; usage errors; and custom output directories.
* Login classification against an in-test stub HTTP server: 500/503 produce `error` and exit 1 in default mode,
  with no password or response body in any output; 401 is a skip (exit 0), which fails under `--require-api`;
  `--offline` makes no requests; a failed login closes its client.

## What CI guarantees

The `Evaluation gates · offline` job in `.github/workflows/ci.yml` deliberately has no service containers. It
runs `pytest -m offline`, then `python -m evals.run --offline`. The job fails if any deterministic gate fails or
errors. The report directory is uploaded as the `evaluation-reports` artifact even after a failure, with
`if: !cancelled()` and no `continue-on-error`, so the failing report is available and the job is still red.

Each kind of guarantee lives in one place:

| Guarantee | Where |
|---|---|
| Deterministic gates (grounding, injection detection, SQL guard), fixture-free and service-free | CI `evals` job |
| Integration behaviour with the fixture LLM against real Postgres + pgvector | CI `backend` job (`pytest`) |
| API gates (retrieval with a real embedding model, numeric correctness) | locally: `make eval EVAL_ARGS=--require-api` |
| Live-model gates | locally: `make eval EVAL_ARGS="--require-api --live"` |

CI doesn't need paid APIs, credentials, downloaded models or live search, so it can't make claims about
model-dependent quality.

## Limitations

* **Small datasets.** Grounding has 6 cases, injection 11, SQL 11, retrieval 10, tool selection 4, and canary
  trials 5. These are regression checks, not benchmarks. With n=10, a single case moves recall by 0.1, and the
  live checks have very wide confidence intervals.
* **Retrieval thresholds are tied to one embedding model.** They were calibrated on `nomic-embed-text`. Changing
  the embedding model means re-measuring. If you run the API checks against a fixture-provider server, they test
  plumbing with hash embeddings, not retrieval quality, and the report says `provider=fixture`.
* **The deterministic sets pass at 100%.** They prove the guards behave as specified on known cases, not that the
  guards are complete (see the follow-ups below).
* The SQL guard cases are in `run.py`, not in `dataset.json`.

## Possible follow-ups (not part of this change)

I checked these against the verifier on the current source with a one-off script:

* Uncited sentences aren't verified. "It also cured cancer." with no `[S#]` produces no claim at all.
* A wrong year passes the numeric check. A claim of "2019" against evidence that says "2024" is still `supported`.
* A wrong small number passes. "2 commercial sites" against "three commercial sites" is `supported`.
* Contradictions pass lexical verification. "did not achieve 91.3 percent" against "achieved 91.3 percent" is
  `supported`.

I haven't verified these yet:

* Verification metadata going stale after a report is edited.
* Missing analyst filters.
* SQL result-cap bypasses.
* Races with queued cancellation.
* Correctness of the tool audit log.
* Larger retrieval sets and reranking experiments.

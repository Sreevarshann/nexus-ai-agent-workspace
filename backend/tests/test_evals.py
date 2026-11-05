"""Evaluation quality gates. Offline: no Postgres, Redis, model or network (``pytest -m offline``).

Unit tests exercise ``evals.gates`` directly; subprocess tests run the real ``python -m evals.run`` CLI and assert
on its exit code and the reports it writes, so the gate logic is never mocked away.
"""

from __future__ import annotations

import copy
import json
import math
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from evals.gates import (
    EXIT_GATE_FAILED,
    EXIT_PASS,
    EXIT_USAGE,
    CheckResult,
    CheckSpec,
    Measurement,
    Outcome,
    RunReport,
    Threshold,
    Unavailable,
    build_report,
    evaluate,
    gate_failures,
    git_info,
    not_executed,
    run_check,
    write_outputs,
)

pytestmark = pytest.mark.offline

BACKEND = Path(__file__).parents[1]
DATASET = json.loads((BACKEND / "evals/dataset.json").read_text())


def spec(*thresholds: Threshold, fn: Any = None, category: str = "deterministic") -> CheckSpec:
    return CheckSpec("demo", category, "demo check", thresholds, fn or (lambda ctx: Measurement({}, 1)))  # type: ignore[arg-type]


AT_LEAST_08 = Threshold(metric="accuracy", op=">=", value=0.8, rationale="test")
AT_MOST_01 = Threshold(metric="leak_rate", op="<=", value=0.1, rationale="test")


# ------------------------------------------------------------------ thresholds and outcomes


@pytest.mark.parametrize(
    ("value", "outcome"),
    [(0.8, Outcome.PASS), (0.9, Outcome.PASS), (math.nextafter(0.8, 0), Outcome.FAIL), (0.0, Outcome.FAIL)],
)
def test_minimum_threshold_boundary(value: float, outcome: Outcome) -> None:
    r = evaluate(spec(AT_LEAST_08), True, Measurement({"accuracy": value}, 10))
    assert r.outcome == outcome
    assert r.gates[0].measured == value and r.gates[0].met is (outcome == Outcome.PASS)


@pytest.mark.parametrize(
    ("value", "outcome"),
    [(0.1, Outcome.PASS), (0.0, Outcome.PASS), (math.nextafter(0.1, 1), Outcome.FAIL), (1.0, Outcome.FAIL)],
)
def test_maximum_threshold_boundary(value: float, outcome: Outcome) -> None:
    assert evaluate(spec(AT_MOST_01), True, Measurement({"leak_rate": value}, 5)).outcome == outcome


def test_every_threshold_must_hold() -> None:
    r = evaluate(spec(AT_LEAST_08, AT_MOST_01), True, Measurement({"accuracy": 1.0, "leak_rate": 0.2}, 5))
    assert r.outcome == Outcome.FAIL
    assert "leak_rate=0.2 (needs <= 0.1)" in (r.reason or "")
    assert [g.met for g in r.gates] == [True, False]


@pytest.mark.parametrize(
    ("metrics", "problem"),
    [
        ({}, "accuracy is missing"),
        ({"accuracy": None}, "accuracy is missing"),
        ({"accuracy": float("nan")}, "not finite"),
        ({"accuracy": float("inf")}, "not finite"),
        ({"accuracy": -float("inf")}, "not finite"),
        ({"accuracy": "1.0"}, "not a number"),
        ({"accuracy": True}, "not a number"),
        ({"accuracy": 1.0, "extra": float("nan")}, "extra is not finite"),
    ],
)
def test_invalid_metrics_are_errors_not_measurements(metrics: dict[str, Any], problem: str) -> None:
    r = evaluate(spec(AT_LEAST_08), True, Measurement(metrics, 10))
    assert r.outcome == Outcome.ERROR
    assert problem in (r.reason or "")
    assert all(math.isfinite(v) for v in r.metrics.values())
    assert gate_failures([r])


@pytest.mark.parametrize("samples", [0, -1, None, True])
def test_measurement_without_samples_is_an_error(samples: Any) -> None:
    r = evaluate(spec(AT_LEAST_08), True, Measurement({"accuracy": 1.0}, samples))
    assert r.outcome == Outcome.ERROR and "sample count" in (r.reason or "")


def test_numpy_values_are_measured_and_serialisable() -> None:
    """Regression: a numpy.bool in case details made the report unwritable after a real API run."""
    np = pytest.importorskip("numpy")
    r = evaluate(
        spec(AT_LEAST_08),
        True,
        Measurement({"accuracy": np.float64(0.9), "n_ok": np.int64(9)}, 10, {"ok": np.bool_(True)}),
    )
    assert r.outcome == Outcome.PASS and r.metrics == {"accuracy": 0.9, "n_ok": 9.0}
    assert json.loads(r.model_dump_json())["details"] == {"ok": True}
    assert evaluate(spec(AT_LEAST_08), True, Measurement({"accuracy": np.bool_(True)}, 1)).outcome == Outcome.ERROR


def test_check_without_thresholds_cannot_pass() -> None:
    assert evaluate(spec(), True, Measurement({"accuracy": 1.0}, 3)).outcome == Outcome.ERROR


def test_execution_error_cannot_pass() -> None:
    def boom(ctx: Any) -> Measurement:
        raise ZeroDivisionError("division by zero")

    r = run_check(spec(AT_LEAST_08, fn=boom), required=False, ctx=None)
    assert r.outcome == Outcome.ERROR and r.reason == "ZeroDivisionError: division by zero"
    assert r.metrics == {} and r.gates == []
    assert gate_failures([r]), "an error fails the run even for an optional check"


def test_unavailable_is_a_visible_skip_and_fails_only_when_required() -> None:
    def down(ctx: Any) -> Measurement:
        raise Unavailable("API not reachable")

    optional = run_check(spec(AT_LEAST_08, fn=down, category="api"), required=False, ctx=None)
    required = run_check(spec(AT_LEAST_08, fn=down, category="api"), required=True, ctx=None)
    assert optional.outcome == required.outcome == Outcome.SKIP
    assert optional.reason == "unavailable: API not reachable"
    assert gate_failures([optional]) == []
    assert gate_failures([required]) == ["demo: required check skipped — unavailable: API not reachable"]


def test_inconsistent_results_are_unrepresentable() -> None:
    base = {"id": "x", "category": "deterministic", "required": True, "thresholds": [AT_LEAST_08], "samples": 3}
    gate = {"metric": "accuracy", "op": ">=", "threshold": 0.8, "measured": 0.1, "met": False}
    with pytest.raises(ValidationError, match="unmet threshold"):
        CheckResult(**base, outcome=Outcome.PASS, metrics={"accuracy": 0.1}, gates=[gate])
    with pytest.raises(ValidationError, match="without a measured gate"):
        CheckResult(**base, outcome=Outcome.PASS, metrics={"accuracy": 1.0})
    with pytest.raises(ValidationError, match="finite"):
        CheckResult(**base, outcome=Outcome.ERROR, reason="r", metrics={"accuracy": float("nan")})
    with pytest.raises(ValidationError, match="requires a reason"):
        CheckResult(**base, outcome=Outcome.SKIP)
    with pytest.raises(ValidationError, match="finite"):
        Threshold(metric="a", op=">=", value=float("nan"), rationale="r")


def _report(checks: list[CheckResult], at: str = "2026-01-01T00:00:00+00:00", run_id: str = "r1") -> RunReport:
    return build_report(
        checks,
        run_id=run_id,
        generated_at=at,
        duration_s=0.0,
        metadata={
            "git": git_info(Path("/nonexistent")),
            "dataset": {"path": "d.json", "sha256": "0" * 64, "sections": {}},
            "config": {},
        },
    )


def test_run_outcome_and_exit_code() -> None:
    ok = evaluate(spec(AT_LEAST_08), True, Measurement({"accuracy": 1.0}, 3))
    skipped = not_executed(spec(AT_LEAST_08), False, Outcome.SKIP, "not requested")
    passing = _report([ok, skipped])
    assert (passing.outcome, passing.exit_code, passing.complete) == ("pass", EXIT_PASS, False)
    assert passing.counts == {"pass": 1, "fail": 0, "skip": 1, "error": 0}
    bad = evaluate(spec(AT_LEAST_08), True, Measurement({"accuracy": 0.0}, 3))
    failing = _report([ok, bad])
    assert (failing.outcome, failing.exit_code, failing.complete) == ("fail", EXIT_GATE_FAILED, True)
    with pytest.raises(ValidationError, match="outcome does not match"):
        RunReport.model_validate({**failing.model_dump(), "outcome": "pass", "failures": [], "exit_code": 0})


def test_missing_metadata_stays_unknown(tmp_path: Path) -> None:
    assert git_info(tmp_path).model_dump() == {"commit": None, "branch": None, "tracked_changes": None}
    assert git_info(BACKEND, git="/nonexistent/git").commit is None
    r = _report([evaluate(spec(AT_LEAST_08), True, Measurement({"accuracy": 1.0}, 3))])
    assert r.metadata.models == [], "no model was used, so none may be claimed"


def test_partial_run_never_replaces_complete_latest(tmp_path: Path) -> None:
    ok = evaluate(spec(AT_LEAST_08), True, Measurement({"accuracy": 1.0}, 3))
    skip = not_executed(spec(AT_LEAST_08), False, Outcome.SKIP, "offline")
    complete = _report([ok], at="2026-01-01T00:00:00+00:00", run_id="a")
    partial = _report([ok, skip], at="2026-01-02T00:00:00+00:00", run_id="b")
    write_outputs(complete, tmp_path)
    written = write_outputs(partial, tmp_path)
    assert "latest" not in written
    assert json.loads((tmp_path / "latest.json").read_text())["run_id"] == "a"
    assert json.loads((tmp_path / "latest-run.json").read_text())["run_id"] == "b"
    assert sorted(p.name for p in (tmp_path / "runs").iterdir()) == ["a.json", "a.md", "b.json", "b.md"]


def test_pointers_never_move_backwards_and_runs_are_never_overwritten(tmp_path: Path) -> None:
    ok = evaluate(spec(AT_LEAST_08), True, Measurement({"accuracy": 1.0}, 3))
    write_outputs(_report([ok], at="2026-01-02T00:00:00+00:00", run_id="newer"), tmp_path)
    write_outputs(_report([ok], at="2026-01-01T00:00:00+00:00", run_id="older"), tmp_path)  # finished late
    assert json.loads((tmp_path / "latest.json").read_text())["run_id"] == "newer"
    with pytest.raises(FileExistsError):
        write_outputs(_report([ok], run_id="older"), tmp_path)


# ------------------------------------------------------------------ the real CLI, as a subprocess


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if not k.startswith(("NEXUS_", "PYTEST"))}
    base["PYTHONPATH"] = os.pathsep.join(["src", "."])
    return subprocess.run(
        [sys.executable, "-m", "evals.run", *args],
        cwd=BACKEND,
        env={**base, **(env or {})},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def latest_run(out: Path) -> dict[str, Any]:
    return json.loads((out / "latest-run.json").read_text())


def checks_by_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in report["checks"]}


def write_dataset(tmp_path: Path, mutate: Any) -> Path:
    data = copy.deepcopy(DATASET)
    mutate(data)
    p = tmp_path / "dataset.json"
    p.write_text(json.dumps(data))
    return p


def test_cli_offline_success(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    p = run_cli("--offline", "--output-dir", str(out))
    assert p.returncode == EXIT_PASS, p.stdout + p.stderr
    rep = latest_run(out)
    checks = checks_by_id(rep)
    assert rep["outcome"] == "pass" and rep["complete"] is False
    assert {k: c["outcome"] for k, c in checks.items() if c["category"] == "deterministic"} == {
        "citation_grounding": "pass",
        "prompt_injection_detection": "pass",
        "sql_guard": "pass",
    }
    assert {c["outcome"] for c in checks.values() if c["category"] != "deterministic"} == {"skip"}
    assert checks["document_retrieval"]["reason"] == "disabled by --offline"
    md = rep["metadata"]
    assert md["dataset"]["sha256"] and md["config"]["offline"] is True and md["config"]["api_url"] is None
    assert md["models"] == []
    assert not (out / "latest.json").exists(), "a partial run must not create the complete-run report"
    assert (out / "latest-run.md").read_text().startswith("# NEXUS AI evaluation")
    assert len(list((out / "runs").glob("*.json"))) == 1


def test_cli_failing_required_metric_exits_nonzero(tmp_path: Path) -> None:
    """Regression: grounding accuracy 0.0 used to be written to latest.json while the command exited 0."""

    def invert(d: dict[str, Any]) -> None:
        for case in d["grounding"]:
            case["expect"] = "unsupported" if case["expect"] == "supported" else "supported"

    out = tmp_path / "reports"
    p = run_cli("--offline", "--dataset", str(write_dataset(tmp_path, invert)), "--output-dir", str(out))
    assert p.returncode == EXIT_GATE_FAILED, p.stdout + p.stderr
    assert "Evaluation FAILED (exit 1)" in p.stderr
    rep = latest_run(out)
    grounding = checks_by_id(rep)["citation_grounding"]
    assert grounding["outcome"] == "fail" and grounding["metrics"]["accuracy"] == 0.0
    assert rep["outcome"] == "fail" and rep["failures"][0].startswith("citation_grounding: fail")
    assert "## Gate failures" in (out / "latest-run.md").read_text()


def test_cli_check_execution_error_exits_nonzero(tmp_path: Path) -> None:
    def break_case(d: dict[str, Any]) -> None:
        del d["grounding"][0]["report"]

    out = tmp_path / "reports"
    p = run_cli("--offline", "--dataset", str(write_dataset(tmp_path, break_case)), "--output-dir", str(out))
    assert p.returncode == EXIT_GATE_FAILED
    c = checks_by_id(latest_run(out))["citation_grounding"]
    assert c["outcome"] == "error" and c["reason"] == "KeyError: 'report'" and c["metrics"] == {}


def test_cli_empty_case_set_is_an_error_not_a_pass(tmp_path: Path) -> None:
    def empty(d: dict[str, Any]) -> None:
        d["grounding"] = []

    out = tmp_path / "reports"
    p = run_cli("--offline", "--dataset", str(write_dataset(tmp_path, empty)), "--output-dir", str(out))
    assert p.returncode == EXIT_GATE_FAILED
    assert checks_by_id(latest_run(out))["citation_grounding"]["outcome"] == "error"


def test_cli_optional_api_unavailable_is_a_visible_skip(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    env = {"NEXUS_DEMO_EMAIL": "demo@nexus.test", "NEXUS_DEMO_PASSWORD": "x"}
    p = run_cli("--api-url", f"http://127.0.0.1:{_closed_port()}/api", "--output-dir", str(out), env=env)
    assert p.returncode == EXIT_PASS, p.stdout + p.stderr
    checks = checks_by_id(latest_run(out))
    for cid in ("document_retrieval", "numeric_correctness"):
        assert checks[cid]["outcome"] == "skip" and checks[cid]["required"] is False
        assert checks[cid]["reason"].startswith("unavailable: API not reachable")


def test_cli_require_api_fails_when_api_unavailable(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    env = {"NEXUS_DEMO_EMAIL": "demo@nexus.test", "NEXUS_DEMO_PASSWORD": "x"}
    p = run_cli(
        "--require-api", "--api-url", f"http://127.0.0.1:{_closed_port()}/api", "--output-dir", str(out), env=env
    )
    assert p.returncode == EXIT_GATE_FAILED
    rep = latest_run(out)
    assert rep["outcome"] == "fail"
    assert {f.split(":")[0] for f in rep["failures"]} == {"document_retrieval", "numeric_correctness"}
    assert all("required check skipped" in f for f in rep["failures"])


def test_cli_live_refuses_fixture_model(tmp_path: Path) -> None:
    """--live must never report the deterministic fixture provider's output as a live-model measurement."""
    out = tmp_path / "reports"
    env = {"NEXUS_ENV": "test", "NEXUS_LLM_PROVIDER": "fixture"}
    p = run_cli("--live", "--api-url", f"http://127.0.0.1:{_closed_port()}/api", "--output-dir", str(out), env=env)
    assert p.returncode == EXIT_GATE_FAILED
    checks = checks_by_id(latest_run(out))
    resist = checks["prompt_injection_resistance"]
    assert resist["required"] is True and resist["outcome"] == "error"
    assert "fixture" in resist["reason"] and resist["metrics"] == {} and resist["model"] is None
    assert checks["tool_selection"]["required"] is True and checks["tool_selection"]["outcome"] == "skip"


def test_cli_usage_errors(tmp_path: Path) -> None:
    assert run_cli("--offline", "--require-api").returncode == EXIT_USAGE
    assert run_cli("--offline", "--live").returncode == EXIT_USAGE
    p = run_cli("--offline", "--dataset", str(tmp_path / "missing.json"), "--output-dir", str(tmp_path))
    assert p.returncode == EXIT_USAGE and "cannot read dataset" in p.stderr


def test_cli_retains_history_in_custom_output_dir(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "reports"
    prior = {"generated_at": "2026-11-04T23:31:43+00:00", "note": "previous complete report"}
    out.mkdir(parents=True)
    (out / "latest.json").write_text(json.dumps(prior))
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "evals.run", "--offline", "--output-dir", str(out)],
            cwd=BACKEND,
            env={**os.environ, "PYTHONPATH": os.pathsep.join(["src", "."])},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(3)
    ]  # concurrent runs
    assert [p.wait(timeout=120) for p in procs] == [0, 0, 0]
    assert run_cli("--offline", "--output-dir", str(out)).returncode == 0
    runs = sorted((out / "runs").glob("*.json"))
    assert len(runs) == 4 and len({json.loads(r.read_text())["run_id"] for r in runs}) == 4
    assert json.loads((out / "latest.json").read_text()) == prior, "partial runs keep the complete report"
    newest = max(runs, key=lambda r: json.loads(r.read_text())["generated_at"])
    assert latest_run(out)["run_id"] == json.loads(newest.read_text())["run_id"]
    assert not list(out.glob(".*.tmp"))


# ------------------------------------------------------------------ login classification against a stub API


class _StubAPI:
    """Real HTTP server standing in for the NEXUS API: answers /auth/login with a fixed status, records requests."""

    def __init__(self, login_status: int):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread

        stub = self
        self.requests: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def _reply(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                stub.requests.append(f"{self.command} {self.path}")
                code = login_status if self.path == "/api/auth/login" else 404
                body = b'{"detail": "boom: internal stack trace with SECRET-IN-BODY"}'
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _reply

            def log_message(self, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/api"
        Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub_api(request: pytest.FixtureRequest) -> Any:
    s = _StubAPI(request.param)
    yield s
    s.close()


DEMO_PASSWORD = "pw-must-never-appear-in-reports"
DEMO_ENV = {"NEXUS_DEMO_EMAIL": "demo@nexus.test", "NEXUS_DEMO_PASSWORD": DEMO_PASSWORD}


def _all_output(p: subprocess.CompletedProcess[str], out: Path) -> str:
    return p.stdout + p.stderr + "".join(f.read_text() for f in out.rglob("*") if f.suffix in (".json", ".md"))


@pytest.mark.parametrize("stub_api", [500, 503], indirect=True)
def test_cli_login_server_error_is_an_error_even_when_api_optional(stub_api: _StubAPI, tmp_path: Path) -> None:
    """Regression: a login HTTP 5xx used to be reported as an optional skip, so a broken API exited 0."""
    out = tmp_path / "reports"
    p = run_cli("--api-url", stub_api.url, "--output-dir", str(out), env=DEMO_ENV)
    assert p.returncode == EXIT_GATE_FAILED, p.stdout + p.stderr
    rep = latest_run(out)
    assert rep["outcome"] == "fail"
    checks = checks_by_id(rep)
    code = stub_api.requests and stub_api.requests[0]
    assert code == "POST /api/auth/login"
    for cid in ("document_retrieval", "numeric_correctness"):
        c = checks[cid]
        assert c["required"] is False and c["outcome"] == "error" and c["metrics"] == {}
        assert c["reason"].startswith("ApiError: demo login failed with HTTP 5")
    assert stub_api.requests.count("POST /api/auth/login") == 1, "the failed login is cached, not retried per check"
    text = _all_output(p, out)
    assert DEMO_PASSWORD not in text and "SECRET-IN-BODY" not in text


@pytest.mark.parametrize("stub_api", [401], indirect=True)
def test_cli_login_rejected_is_an_unavailable_prerequisite(stub_api: _StubAPI, tmp_path: Path) -> None:
    """401 = demo account not seeded / stale credentials: a visible optional skip, a failure under --require-api."""
    out = tmp_path / "optional"
    p = run_cli("--api-url", stub_api.url, "--output-dir", str(out), env=DEMO_ENV)
    assert p.returncode == EXIT_PASS, p.stdout + p.stderr
    checks = checks_by_id(latest_run(out))
    for cid in ("document_retrieval", "numeric_correctness"):
        assert checks[cid]["outcome"] == "skip" and "HTTP 401" in checks[cid]["reason"]
    req_out = tmp_path / "required"
    p = run_cli("--require-api", "--api-url", stub_api.url, "--output-dir", str(req_out), env=DEMO_ENV)
    assert p.returncode == EXIT_GATE_FAILED
    assert all("required check skipped" in f for f in latest_run(req_out)["failures"])
    assert DEMO_PASSWORD not in _all_output(p, req_out)


@pytest.mark.parametrize("stub_api", [200], indirect=True)
def test_cli_offline_never_contacts_the_api(stub_api: _StubAPI, tmp_path: Path) -> None:
    p = run_cli("--offline", "--api-url", stub_api.url, "--output-dir", str(tmp_path), env=DEMO_ENV)
    assert p.returncode == EXIT_PASS, p.stdout + p.stderr
    assert stub_api.requests == []


@pytest.mark.parametrize("stub_api", [500], indirect=True)
def test_failed_login_closes_the_http_client(stub_api: _StubAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    import evals.run as run

    real_client, created = httpx.Client, []

    def tracking_client(*args: Any, **kwargs: Any) -> httpx.Client:
        created.append(real_client(*args, **kwargs))
        return created[-1]

    monkeypatch.setattr(run.httpx, "Client", tracking_client)
    for k, v in DEMO_ENV.items():
        monkeypatch.setenv(k, v)
    ctx = run.Context({}, stub_api.url)
    with pytest.raises(run.ApiError, match="HTTP 500"):
        ctx.api()
    with pytest.raises(run.ApiError):  # cached: no second connection attempt
        ctx.api()
    assert len(created) == 1 and created[0].is_closed

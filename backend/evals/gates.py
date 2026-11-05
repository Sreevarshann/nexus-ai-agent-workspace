"""Evaluation result model, quality gates and report persistence.

The runner (``evals/run.py``) measures; this module decides. Every check produces a validated ``CheckResult`` with
one of four outcomes:

* ``pass``  — the check executed, every metric is a finite number and every threshold is met.
* ``fail``  — the check executed with valid metrics, and at least one threshold is not met.
* ``skip``  — the check did not execute (not requested, or its dependency was unavailable). Never a pass.
* ``error`` — the check raised, or produced missing / non-numeric / non-finite metrics. Never a measurement.

A run fails when any check fails or errors, or when a *required* check is skipped. See docs/EVALUATION.md.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import numbers
import os
import platform
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 2  # 1 = the original free-form latest.json (no outcomes, no thresholds)

EXIT_PASS = 0
EXIT_GATE_FAILED = 1
EXIT_USAGE = 2  # argparse's own code for invalid invocation; also used for an unreadable dataset

Category = Literal["deterministic", "api", "live"]


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


class Unavailable(Exception):
    """A check's dependency (API, seeded data, model) is not available. Becomes a skip, never a pass."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _jsonable(o: Any) -> Any:
    item = getattr(o, "item", None)  # numpy scalar → Python scalar
    return item() if callable(item) else str(o)


def _finite(v: float, what: str) -> float:
    if isinstance(v, bool) or not math.isfinite(v):
        raise ValueError(f"{what} must be a finite number, got {v!r}")
    return float(v)


class Threshold(_Strict):
    metric: str
    op: Literal[">=", "<="]
    value: float
    rationale: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def _value_finite(cls, v: float) -> float:
        return _finite(v, "threshold value")

    def met_by(self, measured: float) -> bool:
        return measured >= self.value if self.op == ">=" else measured <= self.value

    def describe(self) -> str:
        return f"{self.metric} {self.op} {self.value:g}"


class GateResult(_Strict):
    metric: str
    op: Literal[">=", "<="]
    threshold: float
    measured: float
    met: bool


class ModelIdentity(_Strict):
    """A model identity that was actually observed. Fields that were not observed stay ``None``."""

    source: str
    provider: str | None = None
    chat_model: str | None = None
    embed_model: str | None = None


class CheckResult(_Strict):
    id: str
    category: Category
    required: bool
    outcome: Outcome
    description: str = ""
    metrics: dict[str, float] = Field(default_factory=dict)
    samples: int | None = None
    thresholds: list[Threshold] = Field(default_factory=list)
    gates: list[GateResult] = Field(default_factory=list)
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    model: ModelIdentity | None = None
    duration_s: float = 0.0

    @field_validator("details", mode="before")
    @classmethod
    def _details_jsonable(cls, v: dict[str, Any]) -> dict[str, Any]:
        # Case details come from pandas/numpy; store plain JSON so a report can always be written and re-read.
        return dict(json.loads(json.dumps(v, default=_jsonable)))

    @field_validator("metrics")
    @classmethod
    def _metrics_finite(cls, v: dict[str, float]) -> dict[str, float]:
        return {k: _finite(x, f"metric {k!r}") for k, x in v.items()}

    @model_validator(mode="after")
    def _outcome_consistent(self) -> CheckResult:
        """Make an inconsistent result unrepresentable, so no code path can construct a bogus pass."""
        if self.outcome in (Outcome.PASS, Outcome.FAIL):
            gated = {g.metric for g in self.gates}
            missing = [t.metric for t in self.thresholds if t.metric not in gated or t.metric not in self.metrics]
            if missing:
                raise ValueError(f"{self.id}: {self.outcome} without a measured gate for {missing}")
            if not self.thresholds:
                raise ValueError(f"{self.id}: {self.outcome} requires at least one threshold")
            if self.samples is None or self.samples < 1:
                raise ValueError(f"{self.id}: {self.outcome} requires a positive sample count")
            all_met = all(g.met for g in self.gates)
            if self.outcome == Outcome.PASS and not all_met:
                raise ValueError(f"{self.id}: pass with an unmet threshold")
            if self.outcome == Outcome.FAIL and all_met:
                raise ValueError(f"{self.id}: fail although every threshold is met")
        elif not self.reason:
            raise ValueError(f"{self.id}: {self.outcome} requires a reason")
        return self


@dataclass
class Measurement:
    """What a check function returns: raw metrics are validated by ``evaluate``, not trusted."""

    metrics: dict[str, Any]
    samples: int
    details: dict[str, Any] = field(default_factory=dict)
    model: ModelIdentity | None = None


@dataclass(frozen=True)
class CheckSpec:
    id: str
    category: Category
    description: str
    thresholds: tuple[Threshold, ...]
    fn: Callable[[Any], Measurement]


def _invalid_metric(name: str, value: Any) -> str | None:
    if value is None:
        return f"{name} is missing"
    # numbers.Real covers numpy scalars; bools (Python or numpy) are verdicts, not metrics
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return f"{name} is not a number ({type(value).__name__})"
    if not math.isfinite(value):
        return f"{name} is not finite ({value})"
    return None


def evaluate(spec: CheckSpec, required: bool, m: Measurement, duration_s: float = 0.0) -> CheckResult:
    """Apply a spec's thresholds to a measurement. Invalid measurements become ``error``, never ``pass``."""
    base: dict[str, Any] = {
        "id": spec.id,
        "category": spec.category,
        "required": required,
        "description": spec.description,
        "thresholds": list(spec.thresholds),
        "details": m.details,
        "model": m.model,
        "duration_s": round(duration_s, 3),
    }
    problems = [p for t in spec.thresholds if (p := _invalid_metric(t.metric, m.metrics.get(t.metric)))]
    problems += [
        p for k, v in m.metrics.items() if k not in {t.metric for t in spec.thresholds} and (p := _invalid_metric(k, v))
    ]
    if isinstance(m.samples, bool) or not isinstance(m.samples, int) or m.samples < 1:
        problems.append(f"sample count must be a positive integer, got {m.samples!r}")
    if not spec.thresholds:
        problems.append("no thresholds defined")
    if problems:
        valid = {k: float(v) for k, v in m.metrics.items() if _invalid_metric(k, v) is None}
        base.pop("details")
        return CheckResult(
            **base,
            outcome=Outcome.ERROR,
            metrics=valid,
            samples=m.samples if isinstance(m.samples, int) and not isinstance(m.samples, bool) else None,
            reason="invalid measurement: " + "; ".join(problems),
            details={**m.details, "invalid_metrics": {k: repr(v) for k, v in m.metrics.items() if k not in valid}},
        )
    metrics = {k: float(v) for k, v in m.metrics.items()}
    gates = [
        GateResult(
            metric=t.metric, op=t.op, threshold=t.value, measured=metrics[t.metric], met=t.met_by(metrics[t.metric])
        )
        for t in spec.thresholds
    ]
    unmet = [f"{g.metric}={g.measured:g} (needs {g.op} {g.threshold:g})" for g in gates if not g.met]
    return CheckResult(
        **base,
        outcome=Outcome.FAIL if unmet else Outcome.PASS,
        metrics=metrics,
        samples=m.samples,
        gates=gates,
        reason="threshold not met: " + "; ".join(unmet) if unmet else None,
    )


def not_executed(
    spec: CheckSpec, required: bool, outcome: Outcome, reason: str, duration_s: float = 0.0
) -> CheckResult:
    assert outcome in (Outcome.SKIP, Outcome.ERROR)
    return CheckResult(
        id=spec.id,
        category=spec.category,
        required=required,
        description=spec.description,
        thresholds=list(spec.thresholds),
        outcome=outcome,
        reason=reason,
        duration_s=round(duration_s, 3),
    )


def run_check(spec: CheckSpec, required: bool, ctx: Any) -> CheckResult:
    """Execute one check. Unavailability → skip; any other exception → error. Neither can pass."""
    started = time.perf_counter()
    try:
        m = spec.fn(ctx)
    except Unavailable as e:
        return not_executed(spec, required, Outcome.SKIP, f"unavailable: {e}", time.perf_counter() - started)
    except Exception as e:
        return not_executed(spec, required, Outcome.ERROR, f"{type(e).__name__}: {e}", time.perf_counter() - started)
    return evaluate(spec, required, m, time.perf_counter() - started)


def gate_failures(checks: list[CheckResult]) -> list[str]:
    """Human-readable reasons the run fails; empty means the run passes."""
    out = []
    for c in checks:
        if c.outcome in (Outcome.FAIL, Outcome.ERROR):
            out.append(f"{c.id}: {c.outcome} — {c.reason}")
        elif c.outcome == Outcome.SKIP and c.required:
            out.append(f"{c.id}: required check skipped — {c.reason}")
    return out


# ------------------------------------------------------------------ metadata


class GitInfo(_Strict):
    commit: str | None = None
    branch: str | None = None
    tracked_changes: bool | None = None  # None = could not be determined


class DatasetInfo(_Strict):
    path: str
    sha256: str
    version: str | None = None
    sections: dict[str, int]


class RunMetadata(_Strict):
    git: GitInfo
    dataset: DatasetInfo
    config: dict[str, Any]
    models: list[ModelIdentity]
    python: str
    platform: str


class RunReport(_Strict):
    schema_version: int = SCHEMA_VERSION
    run_id: str
    generated_at: str
    duration_s: float
    outcome: Literal["pass", "fail"]
    exit_code: int
    complete: bool  # every defined check executed (none skipped)
    counts: dict[str, int]
    failures: list[str]
    metadata: RunMetadata
    checks: list[CheckResult]

    @model_validator(mode="after")
    def _decision_consistent(self) -> RunReport:
        expected = gate_failures(self.checks)
        if self.failures != expected or (self.outcome == "pass") != (not expected):
            raise ValueError("run outcome does not match its check results")
        if self.exit_code != (EXIT_PASS if self.outcome == "pass" else EXIT_GATE_FAILED):
            raise ValueError("exit code does not match outcome")
        if self.complete != all(c.outcome != Outcome.SKIP for c in self.checks):
            raise ValueError("completeness does not match check results")
        return self


def git_info(cwd: Path, git: str = "git") -> GitInfo:
    def run(*args: str) -> str | None:
        try:
            p = subprocess.run([git, *args], cwd=cwd, capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        return p.stdout.strip() if p.returncode == 0 else None

    commit = run("rev-parse", "HEAD")
    if commit is None:
        return GitInfo()
    status = run("status", "--porcelain", "--untracked-files=no")
    branch = run("rev-parse", "--abbrev-ref", "HEAD")
    return GitInfo(
        commit=commit,
        branch=branch if branch and branch != "HEAD" else None,
        tracked_changes=None if status is None else bool(status),
    )


def dataset_info(path: Path, raw: bytes, data: dict[str, Any]) -> DatasetInfo:
    version = data.get("version")
    return DatasetInfo(
        path=str(path),
        sha256=hashlib.sha256(raw).hexdigest(),
        version=None if version is None else str(version),
        sections={k: len(v) for k, v in data.items() if isinstance(v, list | dict)},
    )


def build_report(
    checks: list[CheckResult], *, run_id: str, generated_at: str, duration_s: float, metadata: dict[str, Any]
) -> RunReport:
    failures = gate_failures(checks)
    models = [c.model for c in checks if c.model is not None]
    return RunReport(
        run_id=run_id,
        generated_at=generated_at,
        duration_s=round(duration_s, 3),
        outcome="fail" if failures else "pass",
        exit_code=EXIT_GATE_FAILED if failures else EXIT_PASS,
        complete=all(c.outcome != Outcome.SKIP for c in checks),
        counts={o.value: sum(c.outcome == o for c in checks) for o in Outcome},
        failures=failures,
        metadata=RunMetadata(
            models=list(dict.fromkeys(models)), python=sys.version.split()[0], platform=platform.platform(), **metadata
        ),
        checks=checks,
    )


# ------------------------------------------------------------------ rendering


def _fmt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def render_markdown(r: RunReport) -> str:
    md = r.metadata
    commit = md.git.commit[:12] if md.git.commit else "unknown"
    dirty = {True: "yes", False: "no", None: "unknown"}[md.git.tracked_changes]
    lines = [
        f"# NEXUS AI evaluation — {r.generated_at[:19]}Z",
        "",
        f"**Result: {r.outcome.upper()}** (exit {r.exit_code}) · "
        + " · ".join(f"{n} {k}" for k, n in r.counts.items())
        + (" · complete run" if r.complete else " · partial run (some checks skipped)"),
        "",
        f"- Run: `{r.run_id}` · {r.duration_s:g}s",
        f"- Commit: `{commit}`"
        + (f" ({md.git.branch})" if md.git.branch else "")
        + f" · uncommitted tracked changes: {dirty}",
        f"- Dataset: `{Path(md.dataset.path).name}` sha256 `{md.dataset.sha256[:12]}`"
        + (f" version {md.dataset.version}" if md.dataset.version else ""),
        "- Mode: " + ", ".join(f"{k}={v}" for k, v in md.config.items()),
        "- Models: "
        + (
            "; ".join(
                f"{m.source}: "
                + ", ".join(f"{k}={getattr(m, k)}" for k in ("provider", "chat_model", "embed_model") if getattr(m, k))
                for m in md.models
            )
            or "none observed (no executed check used a model)"
        ),
        "",
        "| Check | Category | Required | Outcome | Metrics (n) | Thresholds | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in r.checks:
        metrics = ", ".join(f"{k}={_fmt(v)}" for k, v in c.metrics.items())
        if c.samples is not None and metrics:
            metrics += f" (n={c.samples})"
        thresholds = ", ".join(t.describe() for t in c.thresholds)
        reason = (c.reason or "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {c.id} | {c.category} | {'yes' if c.required else 'no'} | **{c.outcome}** | {metrics or '—'} | {thresholds} | {reason or '—'} |"
        )
    if r.failures:
        lines += ["", "## Gate failures", "", *(f"- {f}" for f in r.failures)]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ persistence


@contextlib.contextmanager
def _locked(out_dir: Path) -> Iterator[None]:
    with (out_dir / ".lock").open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _existing_is_newer(path: Path, r: RunReport) -> bool:
    try:
        prev = json.loads(path.read_text())
        return (str(prev.get("generated_at", "")), str(prev.get("run_id", ""))) > (r.generated_at, r.run_id)
    except (OSError, ValueError, AttributeError):
        return False


def write_outputs(r: RunReport, out_dir: Path) -> dict[str, Path]:
    """Write an immutable per-run report and update the pointers.

    * ``runs/<run_id>.json|md`` — every run, created exclusively, never overwritten.
    * ``latest-run.json|md``   — the most recent run of any scope.
    * ``latest.json|md``       — the most recent *complete* run only; a partial run never replaces it.
    Pointer updates are atomic and serialised with a lock, and never move a pointer backwards in time.
    """
    runs = out_dir / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    body, md = r.model_dump_json(indent=2) + "\n", render_markdown(r)
    written: dict[str, Path] = {}
    for suffix, text in (("json", body), ("md", md)):
        p = runs / f"{r.run_id}.{suffix}"
        with p.open("x") as fh:  # exclusive create: concurrent runs cannot clobber each other
            fh.write(text)
        written[f"run_{suffix}"] = p
    with _locked(out_dir):
        pointers = ["latest-run"] + (["latest"] if r.complete else [])
        for name in pointers:
            if _existing_is_newer(out_dir / f"{name}.json", r):
                continue
            _atomic_write(out_dir / f"{name}.json", body)
            _atomic_write(out_dir / f"{name}.md", md)
            written[name] = out_dir / f"{name}.json"
    return written

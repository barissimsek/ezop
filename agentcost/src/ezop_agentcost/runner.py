"""Run fixtures x samples as subprocesses behind the recording proxy and build ``report.json``.

Each run is a fresh process started from ``agent.run`` with ``{fixture}``, ``{output}`` (and optionally
``{run_id}``) filled in. Nothing is imported into agentcost itself, so no state leaks between runs.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ezop_agentcost import __version__
from ezop_agentcost.config import Config, ConfigError, Fixture
from ezop_agentcost.proxy import RecordingProxy
from ezop_agentcost.segments import segment_run, segment_texts
from ezop_agentcost.tokens import TokenCounter, prefetch_anthropic_exact

SCHEMA_VERSION = 1
STDERR_TAIL = 2000


@dataclass
class Variant:
    """One side of a comparison: a source tree plus optional extra environment."""

    name: str
    workdir: Path
    env: dict[str, str] = field(default_factory=dict)
    commit: str | None = None


@dataclass
class _Job:
    variant: Variant
    fixture: Fixture
    sample: int


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", s)[:40]


def load_assertions(cfg: Config, fixtures: list[Fixture], root: Path | None = None) -> dict[str, Callable[..., Any]]:
    """Import the quality module and resolve every fixture's named assertion up front."""
    named = {f.assertion for f in fixtures if f.assertion}
    if not named:
        return {}
    if not cfg.assert_module:
        raise ConfigError(f"fixtures name assertions {sorted(named)} but quality.assert is not set")
    path = (root or cfg.root) / cfg.assert_module
    if not path.is_file():
        raise ConfigError(f"quality.assert: {path} not found")
    spec = importlib.util.spec_from_file_location(f"agentcost_asserts_{abs(hash(str(path)))}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    fns: dict[str, Callable[..., Any]] = {}
    for name in named:
        fn = getattr(module, name, None)
        if not callable(fn):
            raise ConfigError(f"assertion '{name}' not found in {path}")
        fns[name] = fn
    return fns


def run_assertion(fn: Callable[..., Any], output: Any, fixture_input: Any) -> tuple[bool, str | None]:
    """Assertions take ``(output)`` or ``(output, input)``. Returning False or raising fails; None/True passes."""
    try:
        nparams = len(inspect.signature(fn).parameters)
        result = fn(output, fixture_input) if nparams >= 2 else fn(output)
    except AssertionError as e:
        return False, str(e) or "assertion failed"
    except Exception as e:
        return False, f"assertion raised {type(e).__name__}: {e}"
    if result is None or result is True:
        return True, None
    return bool(result), None if result else "assertion returned False"


def _read_output(path: Path) -> Any:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return text


def _kill(proc: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except ProcessLookupError:
        pass


def execute(
    cfg: Config,
    proxy: RecordingProxy,
    job: _Job,
    assertions: dict[str, Callable[..., Any]],
) -> dict[str, Any]:
    """Run one fixture sample and return its run record (raw proxy records under ``_raw``)."""
    run_id = f"{job.variant.name}-{_slug(job.fixture.name)}-s{job.sample}-{uuid.uuid4().hex[:6]}"
    tmp = Path(tempfile.mkdtemp(prefix="agentcost-"))
    fixture_path, output_path = tmp / "fixture.json", tmp / "output"
    fixture_path.write_text(json.dumps(job.fixture.input))
    subs = {"{fixture}": str(fixture_path), "{output}": str(output_path), "{run_id}": run_id}
    args = []
    for a in shlex.split(cfg.agent.run):
        for k, v in subs.items():
            a = a.replace(k, v)
        args.append(a)
    env = {**os.environ, **cfg.agent.env, **job.variant.env, **proxy.env_for(run_id)}
    cwd = job.variant.workdir / cfg.agent.cwd if cfg.agent.cwd else job.variant.workdir
    record: dict[str, Any] = {
        "run_id": run_id,
        "fixture": job.fixture.name,
        "sample": job.sample,
        "status": "ok",
        "exit_code": None,
        "duration_s": None,
        "passed": None,
        "assert_error": None,
        "error": None,
    }
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
        )
    except OSError as e:
        record.update(status="crashed", error=f"could not start agent: {e}")
        record["_raw"] = []
        return record
    try:
        _, stderr = proc.communicate(timeout=cfg.agent.timeout_s)
    except subprocess.TimeoutExpired:
        _kill(proc)
        _, stderr = proc.communicate()
        record.update(status="timeout", error=f"killed after {cfg.agent.timeout_s:g}s")
    record["duration_s"] = round(time.monotonic() - started, 3)
    record["exit_code"] = proc.returncode
    if record["status"] == "ok" and proc.returncode != 0:
        record.update(status="crashed", error=f"agent exited with code {proc.returncode}")
    output: Any = None
    if record["status"] == "ok":
        if output_path.exists():
            output = _read_output(output_path)
        else:
            record.update(status="crashed", error="agent exited 0 but wrote nothing to {output}")
    if record["status"] != "ok":
        record["stderr_tail"] = (stderr or b"").decode("utf-8", errors="replace")[-STDERR_TAIL:]

    record["_raw"] = proxy.recorder.collect(run_id)
    if run_id in proxy.recorder.capped_runs:
        record.update(status="capped", error="spend cap reached during this run")
    if record["status"] == "ok" and job.fixture.assertion:
        record["passed"], record["assert_error"] = run_assertion(
            assertions[job.fixture.assertion], output, job.fixture.input
        )
    for p in (fixture_path, output_path):
        p.unlink(missing_ok=True)
    try:
        tmp.rmdir()
    except OSError:
        pass
    return record


ProgressFn = Callable[[int, int, str, dict[str, Any]], None]


def run_check(
    cfg: Config,
    variants: list[Variant],
    fixtures: list[Fixture],
    samples: int | None = None,
    *,
    keep_payloads: Path | None = None,
    upstreams: dict[str, str] | None = None,
    progress: ProgressFn | None = None,
    counter: TokenCounter | None = None,
) -> dict[str, dict[str, Any]]:
    """Run every variant over every fixture x sample, interleaved, and return one report per variant.

    Jobs are queued sample-major, fixture next, variant innermost, so base and head runs of the same fixture
    execute side by side and see the same tool data and provider state.
    """
    samples = samples or cfg.samples
    assertions = load_assertions(cfg, fixtures)
    prices = cfg.price_table()
    jobs = [_Job(v, fx, s) for s in range(1, samples + 1) for fx in fixtures for v in variants]
    results: list[dict[str, Any] | None] = [None] * len(jobs)
    done = 0
    lock = threading.Lock()

    with RecordingProxy(prices, cfg.spend_cap_usd, keep_payloads, upstreams, cfg.proxy_port) as proxy:

        def work(i: int) -> None:
            nonlocal done
            rec = execute(cfg, proxy, jobs[i], assertions)
            results[i] = rec
            with lock:
                done += 1
                if progress:
                    progress(done, len(jobs), jobs[i].variant.name, rec)

        with ThreadPoolExecutor(max_workers=cfg.agent.concurrency) as pool:
            list(pool.map(work, range(len(jobs))))
        spent, capped = proxy.recorder.spent_usd, proxy.recorder.capped
        upstream_anthropic = proxy.upstreams["anthropic"]

    counter = counter or TokenCounter()
    if cfg.token_counts == "exact":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ConfigError("token_counts: exact needs ANTHROPIC_API_KEY for the count_tokens endpoint")
        items = [
            (m, t)
            for rec in results
            for m, t in segment_texts([r for r in rec["_raw"] if r.get("api") == "anthropic.messages"])  # type: ignore[index]
        ]
        if items:
            prefetch_anthropic_exact(counter, items, api_key, base_url=upstream_anthropic)

    reports: dict[str, dict[str, Any]] = {}
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for v in variants:
        runs = []
        for job, rec in zip(jobs, results):
            if job.variant is not v or rec is None:
                continue
            raw = rec.pop("_raw")
            rec["calls"] = segment_run(raw, counter)
            runs.append(rec)
        reports[v.name] = build_report(cfg, v, fixtures, samples, runs, counter, spent, capped, created)
    return reports


def build_report(
    cfg: Config,
    variant: Variant,
    fixtures: list[Fixture],
    samples: int,
    runs: list[dict[str, Any]],
    counter: TokenCounter,
    spent: float,
    capped: bool,
    created: str,
) -> dict[str, Any]:
    warnings: list[str] = []
    ok_runs = [r for r in runs if r["status"] == "ok"]
    zero = [r for r in ok_runs if not r["calls"]]
    if zero:
        warnings.append(
            f"{len(zero)} run(s) recorded zero LLM calls. Does the agent build its client from ANTHROPIC_BASE_URL / "
            "OPENAI_BASE_URL? Hard-coded endpoints and custom HTTP clients bypass the proxy."
        )
    failed = [r for r in runs if r["status"] != "ok"]
    if failed:
        kinds: dict[str, int] = {}
        for r in failed:
            kinds[r["status"]] = kinds.get(r["status"], 0) + 1
        warnings.append("failed runs: " + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())))
    calls = [c for r in runs for c in r["calls"]]
    estimated = sum(1 for c in calls if c.get("estimated") and c.get("segments"))
    if estimated:
        warnings.append(f"{estimated} call(s) reported no usage; their tokens are local estimates")
    if any(c.get("unresolved_context") for c in calls):
        warnings.append(
            "some Responses API calls chain to a response this run did not record; that context is 'mutated'"
        )
    if capped:
        warnings.append(f"spend cap of ${cfg.spend_cap_usd:.2f} was reached; the check is marked capped")
    return {
        "schema_version": SCHEMA_VERSION,
        "agentcost_version": __version__,
        "name": cfg.display_name(),
        "variant": variant.name,
        "commit": variant.commit,
        "created_at": created,
        "samples": samples,
        "fixtures": [f.name for f in fixtures],
        "token_counting": counter.describe(),
        "spend_usd": round(spent, 6),
        "capped": capped,
        "agent": {"run": cfg.agent.run},
        "runs": runs,
        "warnings": warnings,
    }


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1))


def read_report(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise ConfigError(f"cannot read report {path}: {e}") from e
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ConfigError(f"{path}: unsupported report schema_version {data.get('schema_version')}")
    return data

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "support_agent"
sys.path.insert(0, str(EXAMPLE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Agent subprocesses run `python`; make that this interpreter so they see the installed SDKs.
os.environ["PATH"] = os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")


@pytest.fixture(scope="session")
def mock_claude():
    from mock_claude import create_app

    from ezop_agentcost.proxy import ServerThread

    app = create_app(noise=0.0)
    server = ServerThread(app).start()
    yield server, app.state.mock
    server.stop()


@pytest.fixture(scope="session")
def fake_openai():
    from fake_openai import create_app

    from ezop_agentcost.proxy import ServerThread

    server = ServerThread(create_app()).start()
    yield server
    server.stop()


def make_call(segments: list[tuple[str, float, float, float]], output: int, model: str = "claude-opus-5-5") -> dict:
    """A segmented call. segments: (key, tokens, cache_read, cache_write)."""
    total = sum(s[1] for s in segments)
    read = sum(s[2] for s in segments)
    write = sum(s[3] for s in segments)
    return {
        "seq": 1,
        "api": "anthropic.messages",
        "model": model,
        "status": 200,
        "usage": {
            "input": round(total - read - write),
            "cache_read": round(read),
            "cache_write_5m": round(write),
            "cache_write_1h": 0,
            "output": output,
        },
        "segments": [{"key": k, "tokens": t, "cache_read": r, "cache_write": w} for k, t, r, w in segments],
    }


def make_run(fixture: str, calls: list[dict], sample: int = 1, status: str = "ok", passed: Any = True) -> dict:
    return {"fixture": fixture, "sample": sample, "status": status, "passed": passed, "calls": calls}


def make_report(runs: list[dict], **kw: Any) -> dict:
    return {"schema_version": 1, "name": "test", "samples": 3, "runs": runs, "warnings": [], **kw}

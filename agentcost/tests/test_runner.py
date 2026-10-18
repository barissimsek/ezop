"""The subprocess runner: statuses, assertions, zero-call warnings, exact token counting."""

import json
import textwrap

import pytest

from ezop_agentcost.config import ConfigError, parse_config
from ezop_agentcost.runner import Variant, run_check
from ezop_agentcost.tokens import TokenCounter

AGENT = textwrap.dedent(
    """
    import json, os, sys, time
    import anthropic
    args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
    task = json.load(open(args["--input"]))
    mode = task.get("mode", "ok")
    if mode == "crash":
        sys.exit(3)
    if mode == "hang":
        time.sleep(30)
    if mode != "silent":
        client = anthropic.Anthropic(api_key="test", max_retries=0)
        r = client.messages.create(model="claude-opus-5-5", max_tokens=50,
                                   messages=[{"role": "user", "content": task["message"]}])
        answer = "".join(b.text for b in r.content if b.type == "text")
    else:
        answer = "no model needed"
    open(args["--output"], "w").write(json.dumps({"answer": answer}))
    """
)

ASSERTS = textwrap.dedent(
    """
    def mentions_order(output, fixture_input):
        assert "1042" in output["answer"], "no order id"

    def always_false(output):
        return False
    """
)


def setup(tmp_path, fixtures):
    (tmp_path / "agent.py").write_text(AGENT)
    (tmp_path / "asserts.py").write_text(ASSERTS)
    (tmp_path / "fx").mkdir()
    for name, data in fixtures.items():
        (tmp_path / "fx" / f"{name}.json").write_text(json.dumps(data))
    raw = {
        "agent": {"run": "python agent.py --input {fixture} --output {output}", "timeout_s": 3, "concurrency": 4},
        "fixtures": "fx/*.json",
        "samples": 2,
        "quality": {"assert": "asserts.py"},
    }
    return parse_config(raw, tmp_path)


def test_statuses_assertions_and_warnings(tmp_path, mock_claude):
    server, _ = mock_claude
    cfg = setup(
        tmp_path,
        {
            "good": {"input": {"message": "order 1042 is late"}, "assert": "mentions_order"},
            "bad_assert": {"input": {"message": "order 1042"}, "assert": "always_false"},
            "crash": {"input": {"mode": "crash"}},
            "hang": {"input": {"mode": "hang"}},
            "silent": {"input": {"mode": "silent"}},
        },
    )
    reports = run_check(
        cfg,
        [Variant("head", tmp_path)],
        cfg.load_fixtures(),
        upstreams={"anthropic": server.url, "openai": "http://127.0.0.1:9"},
        counter=TokenCounter(prefer="heuristic"),
    )
    report = reports["head"]
    by = {}
    for r in report["runs"]:
        by.setdefault(r["fixture"], []).append(r)
    assert all(r["status"] == "ok" and r["passed"] is True and len(r["calls"]) == 1 for r in by["good"])
    assert all(r["passed"] is False and r["assert_error"] == "assertion returned False" for r in by["bad_assert"])
    assert all(r["status"] == "crashed" and r["exit_code"] == 3 for r in by["crash"])
    assert all(r["status"] == "timeout" for r in by["hang"])
    assert all(r["status"] == "ok" and r["calls"] == [] for r in by["silent"])
    assert any("zero LLM calls" in w for w in report["warnings"])
    assert any("failed runs" in w for w in report["warnings"])
    assert report["samples"] == 2 and len(report["runs"]) == 10
    seg_keys = {s["key"] for s in by["good"][0]["calls"][0]["segments"]}
    assert {"user_input", "overhead"} <= seg_keys


def test_missing_assertion_is_a_config_error(tmp_path):
    cfg = setup(tmp_path, {"x": {"input": {}, "assert": "nope"}})
    with pytest.raises(ConfigError, match="'nope' not found"):
        run_check(cfg, [Variant("head", tmp_path)], cfg.load_fixtures())


def test_exact_token_counts_use_count_tokens(tmp_path, mock_claude, monkeypatch):
    server, _ = mock_claude
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    cfg = setup(tmp_path, {"good": {"input": {"message": "order 1042 please"}}})
    cfg.token_counts = "exact"
    cfg.samples = 1
    counter = TokenCounter(prefer="heuristic")
    report = run_check(
        cfg, [Variant("head", tmp_path)], cfg.load_fixtures(), upstreams={"anthropic": server.url, "openai": "x"},
        counter=counter,
    )["head"]  # fmt: skip
    assert "anthropic-count-tokens" in report["token_counting"]


@pytest.mark.parametrize(
    "raw,match",
    [
        ({"fixtures": "x"}, "agent.run is required"),
        ({"agent": {"run": "python a.py"}, "fixtures": "x"}, "placeholders"),
        ({"agent": {"run": "a {fixture} {output}"}, "fixtures": "x", "bogus": 1}, "unknown config keys"),
        ({"agent": {"run": "a {fixture} {output}"}, "fixtures": "x", "baseline": "sometimes"}, "baseline"),
    ],
)
def test_config_validation(tmp_path, raw, match):
    with pytest.raises(ConfigError, match=match):
        parse_config(raw, tmp_path)


def test_config_percentages(tmp_path):
    cfg = parse_config(
        {"agent": {"run": "a {fixture} {output}"}, "fixtures": "x", "budgets": {"max_regression": "20%"},
         "quality": {"max_quality_drop": 0.03}, "spend_cap_usd": "$12"},
        tmp_path,
    )  # fmt: skip
    assert (cfg.max_regression, cfg.max_quality_drop, cfg.spend_cap_usd) == (0.2, 0.03, 12.0)

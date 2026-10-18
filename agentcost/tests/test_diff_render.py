"""diff_reports on synthetic reports: verdicts, budgets, quality, failures, rendering."""

import random

import pytest
from conftest import make_call, make_report, make_run

from ezop_agentcost.diff import DiffOptions, diff_reports, drift_check
from ezop_agentcost.pricing import PriceTable
from ezop_agentcost.render import MARKER, render_markdown, summary_text

PRICES = PriceTable()


def suite(tool_tokens: float, fixtures: int = 8, samples: int = 3, seed: int = 0, passed: bool = True, noise=0.03):
    rng = random.Random(seed)
    runs = []
    for f in range(fixtures):
        for s in range(samples):
            jitter = 1 + rng.gauss(0, noise)
            calls = []
            carried = 0.0
            for step in range(4):
                segs = [("overhead", 320, 320, 0), ("system_prompt", 1500, 1500, 0), ("user_input", 40, 0, 0)]
                if step:
                    segs.append(("tool_result:lookup_order#1", carried, 0, 0))
                calls.append(make_call(segs, int(80 * jitter)))
                carried = tool_tokens * (1 + 0.1 * f)
            runs.append(make_run(f"fx{f}", calls, sample=s, passed=passed))
    return make_report(runs)


def test_regression_is_gated_and_explained():
    d = diff_reports(suite(500), suite(2000, seed=1), PRICES, DiffOptions(iterations=300))
    assert d["verdict"] == "regression" and d["exit_code"] == 1
    top = d["attribution"]["findings"][0]
    assert top["subject"] == "tool_result:lookup_order"
    assert "grew" in top["sentence"] and "carried through 3 calls" in top["sentence"]
    a = d["attribution"]
    assert sum(c["value"] for c in a["contributions"]) == pytest.approx(a["modeled_delta"], abs=1e-12)
    assert a["residual"] == pytest.approx(0, abs=1e-9)


def test_noop_is_not_gated():
    d = diff_reports(suite(500), suite(500, seed=1), PRICES, DiffOptions(iterations=300))
    assert d["verdict"] in ("ok", "inconclusive") and d["exit_code"] == 0


def test_absolute_budget_and_quality_drop():
    d = diff_reports(
        suite(500),
        suite(500, seed=1, passed=False),
        PRICES,
        DiffOptions(iterations=300, cost_per_run_p50=0.0001),
    )
    assert d["budgets"]["cost_per_run_p50"]["verdict"] == "regression"
    assert d["quality"]["verdict"] == "regression"
    assert d["exit_code"] == 1


def test_failed_runs_are_excluded_and_reported():
    head = suite(500, seed=1)
    for r in head["runs"][:5]:
        r["status"] = "crashed"
    d = diff_reports(suite(500), head, PRICES, DiffOptions(iterations=100))
    assert d["failures"]["head"] == {"crashed": 5}
    assert "Failed runs" in render_markdown(d)


def test_no_common_fixture_is_an_error():
    base = suite(500)
    head = suite(500)
    for r in head["runs"]:
        r["status"] = "timeout"
    d = diff_reports(base, head, PRICES)
    assert d["exit_code"] == 2 and "could not compare" in summary_text(d)


def test_render_markdown_has_marker_summary_and_details():
    d = diff_reports(suite(500), suite(2000, seed=1), PRICES, DiffOptions(iterations=200))
    md = render_markdown(d)
    assert md.startswith(MARKER)
    assert "Cost per run" in md and "REGRESSION" in md and "<details>" in md
    assert "tool_result:lookup_order grew" in md  # backticks stripped inside the text block


def test_drift_check_flags_tool_result_growth_only():
    assert drift_check(suite(500), suite(500, seed=1), PRICES, 0.10) == []
    reasons = drift_check(suite(500), suite(900, seed=1), PRICES, 0.10)
    assert reasons and "tool_result:lookup_order" in reasons[0]

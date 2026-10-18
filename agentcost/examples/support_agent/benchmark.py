"""Seeded-regression benchmark: does agentcost blame the right factor?

Each scenario runs the reference agent twice per fixture sample, interleaved: base (no variant) and head (one
seeded change via SUPPORT_AGENT_VARIANT). The diff's attribution must give the expected factor at least the
expected share of the modeled delta.

    python benchmark.py               # offline, against mock_claude (free, deterministic enough for CI)
    python benchmark.py --live        # real Anthropic API (needs ANTHROPIC_API_KEY; costs money)
    python benchmark.py --exact       # exact token counts via count_tokens (the mock serves it too)
    python benchmark.py -s longer_prompt -n 2
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ezop_agentcost.config import load_config
from ezop_agentcost.diff import DiffOptions, diff_reports
from ezop_agentcost.proxy import ServerThread
from ezop_agentcost.render import summary_text
from ezop_agentcost.runner import Variant, run_check

HERE = Path(__file__).resolve().parent


def share(result: dict[str, Any], group: str, family: str | None = None) -> float:
    a = result["attribution"]
    delta = a["modeled_delta"]
    if not delta:
        return 0.0
    if family is None:
        return a["groups"][group] / delta
    return sum(c["value"] for c in a["contributions"] if c["group"] == group and c["family"] == family) / delta


@dataclass
class Scenario:
    id: int
    variant: str
    change: str
    expectation: str
    check: Callable[[dict[str, Any]], tuple[float, bool]]
    # Offline only: output-length noise in the mock. Attribution scenarios run noise-free so a small true effect
    # (a cached prompt growing, say) is not swamped by random output length; the no-op scenario keeps noise to
    # test that run-to-run variance never gates.
    mock_noise: float = 0.0


def _at_least(group: str, family: str | None, minimum: float) -> Callable[[dict[str, Any]], tuple[float, bool]]:
    def check(result: dict[str, Any]) -> tuple[float, bool]:
        s = share(result, group, family)
        return s, s >= minimum

    return check


def _no_gate(result: dict[str, Any]) -> tuple[float, bool]:
    return result["cost"]["p50_change"]["point"], result["exit_code"] == 0 and result["verdict"] != "regression"


SCENARIOS = [
    Scenario(1, "full_line_items", "tool returns full line_items (~4x)",
             "size of tool_result:lookup_order >= 80%", _at_least("size", "tool_result:lookup_order", 0.80)),
    Scenario(2, "longer_prompt", "system prompt +600 tokens",
             "size of system_prompt >= 90%", _at_least("size", "system_prompt", 0.90)),
    Scenario(3, "timestamp_top", "timestamp moved to the top of the prompt",
             "cache >= 80%", _at_least("cache", None, 0.80)),
    Scenario(4, "extra_refine", "one extra refinement iteration",
             "appearances >= 50%", _at_least("appearances", None, 0.50)),
    Scenario(5, "pricier_model", "model swapped to a pricier tier",
             "price >= 90%", _at_least("price", None, 0.90)),
    Scenario(6, "noop", "no-op refactor", "no gate", _no_gate, mock_noise=0.3),
]  # fmt: skip


def run_scenario(
    scenario: Scenario,
    upstreams: dict[str, str] | None,
    samples: int | None,
    fixtures: list[str] | None,
    exact: bool = False,
) -> dict[str, Any]:
    cfg = load_config(HERE / "agentcost.yml")
    if exact:
        cfg.token_counts = "exact"
    fx = cfg.load_fixtures(only=fixtures)
    variants = [
        Variant("base", HERE, env={"SUPPORT_AGENT_VARIANT": ""}),
        Variant("head", HERE, env={"SUPPORT_AGENT_VARIANT": scenario.variant}),
    ]
    # Warm the prompt cache for both sides first, then measure: the benchmark checks steady-state attribution,
    # not the one-time cache writes a brand-new prompt prefix pays on its first calls.
    run_check(cfg, variants, fx[:1], 1, upstreams=upstreams)
    reports = run_check(cfg, variants, fx, samples, upstreams=upstreams)
    return diff_reports(reports["base"], reports["head"], cfg.price_table(), DiffOptions.from_config(cfg))


def run_benchmark(
    live: bool = False,
    only: list[str] | None = None,
    samples: int | None = None,
    fixtures: list[str] | None = None,
    verbose: bool = False,
    exact: bool = False,
) -> list[tuple[Scenario, dict[str, Any], float, bool]]:
    sys.path.insert(0, str(HERE))
    # agentcost.yml says `python`; make that the interpreter running the benchmark (and its installed SDK).
    os.environ["PATH"] = os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")
    out = []
    server = None
    upstreams = None
    if not live:
        from mock_claude import create_app

        os.environ.setdefault("ANTHROPIC_API_KEY", "mock-key")  # the mock ignores it; the SDK insists on one
        app = create_app()
        server = ServerThread(app).start()
        upstreams = {"anthropic": server.url, "openai": "http://127.0.0.1:9"}
    try:
        for sc in SCENARIOS:
            if only and sc.variant not in only:
                continue
            if server:
                app.state.mock.noise = sc.mock_noise
                app.state.mock.cache.clear()  # each scenario is an independent experiment
            result = run_scenario(sc, upstreams, samples, fixtures, exact)
            if result["verdict"] == "error":
                raise RuntimeError(f"scenario {sc.variant}: {result['error']}; warnings: {result['warnings']}")
            value, passed = sc.check(result)
            out.append((sc, result, value, passed))
            if verbose:
                print(f"\n=== {sc.id}. {sc.change} ===\n{summary_text(result)}\n")
    finally:
        if server:
            server.stop()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="use the real Anthropic API instead of the mock")
    parser.add_argument("-s", "--scenario", action="append", help="variant name to run (repeatable)")
    parser.add_argument("-n", "--samples", type=int)
    parser.add_argument("--exact", action="store_true", help="token_counts: exact (count_tokens endpoint)")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()
    results = run_benchmark(args.live, args.scenario, args.samples, verbose=not args.quiet, exact=args.exact)
    print(f"{'#':<3}{'seeded change':<42}{'expected':<40}{'measured':>9}  result")
    for sc, _, value, passed in results:
        measured = f"{value:+.0%}" if sc.variant == "noop" else f"{value:.0%}"
        print(f"{sc.id:<3}{sc.change:<42}{sc.expectation:<40}{measured:>9}  {'PASS' if passed else 'FAIL'}")
    sys.exit(0 if all(p for *_, p in results) else 1)


if __name__ == "__main__":
    main()

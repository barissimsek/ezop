"""Compare a base report with a head report: statistics, gating, attribution, explanation."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any

from ezop_agentcost import __version__
from ezop_agentcost.attribution import GROUPS, Factors, decompose, modeled_cost, pooled_factors, run_billed_cost
from ezop_agentcost.config import Config
from ezop_agentcost.explain import FamilySummary, SideSummary, build_findings
from ezop_agentcost.pricing import PriceTable, UnknownModelError
from ezop_agentcost.stats import (
    INCONCLUSIVE,
    OK,
    REGRESSION,
    Interval,
    bootstrap_difference,
    bootstrap_relative_change,
    bootstrap_value,
    mean_metric,
    p50_metric,
    p90_metric,
    verdict,
)

EXIT_OK, EXIT_REGRESSION, EXIT_ERROR = 0, 1, 2


@dataclass
class DiffOptions:
    max_regression: float = 0.15
    cost_per_run_p50: float | None = None
    cost_per_run_p90: float | None = None
    max_quality_drop: float = 0.05
    iterations: int = 2000
    seed: int = 20261017

    @classmethod
    def from_config(cls, cfg: Config) -> DiffOptions:
        return cls(
            max_regression=cfg.max_regression,
            cost_per_run_p50=cfg.cost_per_run_p50,
            cost_per_run_p90=cfg.cost_per_run_p90,
            max_quality_drop=cfg.max_quality_drop,
        )


def ok_runs_by_fixture(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in report["runs"]:
        if r["status"] == "ok":
            out.setdefault(r["fixture"], []).append(r)
    return out


def failure_counts(report: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in report["runs"]:
        if r["status"] != "ok":
            counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def _summarize(factors: list[Factors]) -> SideSummary:
    """Average per-fixture factors into one side summary for explanations."""
    n = len(factors)
    side = SideSummary()
    fams = {f for fx in factors for f in fx.families}
    for fam in fams:
        tok = sum(fx.family(fam).S * fx.family(fam).A for fx in factors) / n
        app = sum(fx.family(fam).A for fx in factors) / n
        inst = sum(fx.family(fam).instances for fx in factors) / n
        side.families[fam] = FamilySummary(S=tok / app if app else 0.0, A=app, instances=inst)
    side.output_tokens = sum(fx.O for fx in factors) / n
    side.steps = sum(fx.steps for fx in factors) / n
    total = sum(ff.S * ff.A for fx in factors for ff in fx.families.values())
    read = sum(ff.S * ff.A * ff.R for fx in factors for ff in fx.families.values())
    write = sum(ff.S * ff.A * ff.W for fx in factors for ff in fx.families.values())
    side.cache_hit_rate = read / total if total else 0.0
    side.cache_write_rate = write / total if total else 0.0
    models: dict[str, float] = {}
    for fx in factors:
        for m, s in fx.models.items():
            models[m] = models.get(m, 0.0) + s / n
    side.models = models
    return side


def diff_reports(
    base: dict[str, Any], head: dict[str, Any], prices: PriceTable, opts: DiffOptions | None = None
) -> dict[str, Any]:
    opts = opts or DiffOptions()
    b_runs, h_runs = ok_runs_by_fixture(base), ok_runs_by_fixture(head)
    fixtures = sorted(set(b_runs) & set(h_runs))
    result: dict[str, Any] = {
        "agentcost_version": __version__,
        "name": head.get("name") or base.get("name"),
        "base": {"commit": base.get("commit"), "created_at": base.get("created_at"), "runs": len(base["runs"])},
        "head": {"commit": head.get("commit"), "created_at": head.get("created_at"), "runs": len(head["runs"])},
        "samples": head.get("samples"),
        "fixtures": fixtures,
        "unmatched_fixtures": {
            "base_only": sorted(set(b_runs) - set(h_runs)),
            "head_only": sorted(set(h_runs) - set(b_runs)),
        },
        "failures": {"base": failure_counts(base), "head": failure_counts(head)},
        "token_counting": {"base": base.get("token_counting"), "head": head.get("token_counting")},
        "price_table": prices.version,
        "capped": bool(base.get("capped") or head.get("capped")),
        "warnings": sorted(set(base.get("warnings", [])) | set(head.get("warnings", []))),
        "options": opts.__dict__,
    }
    if not fixtures:
        result.update(verdict="error", exit_code=EXIT_ERROR, error="no fixture has a successful run on both sides")
        return result

    try:
        b_cost = {fx: [run_billed_cost(r, prices) for r in b_runs[fx]] for fx in fixtures}
        h_cost = {fx: [run_billed_cost(r, prices) for r in h_runs[fx]] for fx in fixtures}
        b_factors = {fx: pooled_factors(b_runs[fx], prices) for fx in fixtures}
        h_factors = {fx: pooled_factors(h_runs[fx], prices) for fx in fixtures}
    except UnknownModelError as e:
        result.update(verdict="error", exit_code=EXIT_ERROR, error=str(e.args[0]))
        return result

    kw = {"iterations": opts.iterations, "seed": opts.seed}
    p50 = bootstrap_relative_change(b_cost, h_cost, p50_metric, **kw)
    p90 = bootstrap_relative_change(b_cost, h_cost, p90_metric, **kw)
    cost = {
        "base_p50": p50_metric(b_cost),
        "head_p50": p50_metric(h_cost),
        "base_p90": p90_metric(b_cost),
        "head_p90": p90_metric(h_cost),
        "base_mean": mean_metric(b_cost),
        "head_mean": mean_metric(h_cost),
        "p50_change": p50.to_dict(),
        "p90_change": p90.to_dict(),
        "p50_verdict": verdict(p50, opts.max_regression),
        "p90_verdict": verdict(p90, opts.max_regression),
    }
    result["cost"] = cost

    budgets: dict[str, Any] = {}
    for name, limit, metric in (
        ("cost_per_run_p50", opts.cost_per_run_p50, p50_metric),
        ("cost_per_run_p90", opts.cost_per_run_p90, p90_metric),
    ):
        if limit is None:
            continue
        iv = bootstrap_value(h_cost, metric, **kw)
        budgets[name] = {"limit": limit, "head": iv.to_dict(), "verdict": verdict(iv, limit)}
    result["budgets"] = budgets

    result["quality"] = _quality(b_runs, h_runs, fixtures, opts, kw)

    b_steps = mean(len([c for c in r["calls"] if c.get("segments")]) for fx in fixtures for r in b_runs[fx])
    h_steps = mean(len([c for c in r["calls"] if c.get("segments")]) for fx in fixtures for r in h_runs[fx])
    result["steps"] = {"base": b_steps, "head": h_steps}

    # Attribution: per fixture, then averaged (Shapley is linear, so sums stay exact).
    contrib: dict[tuple[str, str], float] = {}
    modeled_delta = billed_delta = 0.0
    per_fixture: dict[str, Any] = {}
    for fx in fixtures:
        fb, fh = b_factors[fx], h_factors[fx]
        c = decompose(fb, fh)
        for k, v in c.items():
            contrib[k] = contrib.get(k, 0.0) + v / len(fixtures)
        md = modeled_cost(fh) - modeled_cost(fb)
        bd = fh.billed - fb.billed
        modeled_delta += md / len(fixtures)
        billed_delta += bd / len(fixtures)
        per_fixture[fx] = {
            "base_mean_cost": fb.billed,
            "head_mean_cost": fh.billed,
            "modeled_delta": md,
            "base_runs": fb.runs,
            "head_runs": fh.runs,
        }
    groups: dict[str, float] = dict.fromkeys(GROUPS, 0.0)
    for (g, _), v in contrib.items():
        groups[g] += v
    base_side = _summarize(list(b_factors.values()))
    head_side = _summarize(list(h_factors.values()))
    findings = build_findings(contrib, base_side, head_side)
    result["attribution"] = {
        "modeled_delta": modeled_delta,
        "billed_delta": billed_delta,
        "residual": billed_delta - modeled_delta,
        "groups": groups,
        "contributions": [
            {"group": g, "family": f, "value": v} for (g, f), v in sorted(contrib.items(), key=lambda kv: -abs(kv[1]))
        ],
        "findings": [f.to_dict() for f in findings],
        "per_fixture": per_fixture,
        "cache_hit_rate": {"base": base_side.cache_hit_rate, "head": head_side.cache_hit_rate},
        "output_tokens": {"base": base_side.output_tokens, "head": head_side.output_tokens},
    }

    verdicts = [cost["p50_verdict"], cost["p90_verdict"]] + [b["verdict"] for b in budgets.values()]
    if result["quality"].get("verdict"):
        verdicts.append(result["quality"]["verdict"])
    if REGRESSION in verdicts:
        overall = REGRESSION
    elif INCONCLUSIVE in verdicts:
        overall = INCONCLUSIVE
    else:
        overall = OK
    result["verdict"] = overall
    result["exit_code"] = EXIT_REGRESSION if overall == REGRESSION else EXIT_OK
    return result


def _quality(
    b_runs: dict[str, list[dict[str, Any]]],
    h_runs: dict[str, list[dict[str, Any]]],
    fixtures: list[str],
    opts: DiffOptions,
    kw: dict[str, Any],
) -> dict[str, Any]:
    def passes(runs: list[dict[str, Any]]) -> list[float]:
        return [1.0 if r["passed"] else 0.0 for r in runs if r.get("passed") is not None]

    b = {fx: passes(b_runs[fx]) for fx in fixtures}
    h = {fx: passes(h_runs[fx]) for fx in fixtures}
    graded = [fx for fx in fixtures if b[fx] and h[fx]]
    if not graded:
        return {"graded_fixtures": 0}
    b = {fx: b[fx] for fx in graded}
    h = {fx: h[fx] for fx in graded}
    drop: Interval = bootstrap_difference(b, h, mean_metric, **kw)
    return {
        "graded_fixtures": len(graded),
        "base_pass_rate": mean_metric(b),
        "head_pass_rate": mean_metric(h),
        "drop": drop.to_dict(),
        "max_quality_drop": opts.max_quality_drop,
        "verdict": verdict(drop, opts.max_quality_drop),
    }


def drift_check(cached_base: dict[str, Any], head: dict[str, Any], prices: PriceTable, threshold: float) -> list[str]:
    """Signals that the world changed between a cached baseline and today's head run.

    Returns human-readable reasons; an empty list means no drift suspected. Checks every ``tool_result`` family's
    tokens per run and the step count, using the same bootstrap rule as gating with a lower threshold.
    """
    b_runs, h_runs = ok_runs_by_fixture(cached_base), ok_runs_by_fixture(head)
    fixtures = sorted(set(b_runs) & set(h_runs))
    if not fixtures:
        return ["no fixtures in common with the cached baseline"]
    reasons: list[str] = []

    def per_run(runs: dict[str, list[dict[str, Any]]], pick: Any) -> dict[str, list[float]]:
        return {fx: [pick(r) for r in runs[fx]] for fx in fixtures}

    def steps(r: dict[str, Any]) -> float:
        return float(len([c for c in r["calls"] if c.get("segments")]))

    def changed(base_vals: dict[str, list[float]], head_vals: dict[str, list[float]]) -> Interval | None:
        if mean_metric(base_vals) == 0 and mean_metric(head_vals) == 0:
            return None
        if mean_metric(base_vals) == 0:
            return Interval(float("inf"), float("inf"), float("inf"))
        iv = bootstrap_relative_change(base_vals, head_vals, mean_metric, iterations=500)
        return iv if (iv.low > threshold or iv.high < -threshold) else None

    iv = changed(per_run(b_runs, steps), per_run(h_runs, steps))
    if iv:
        reasons.append(f"steps per run changed {iv.point:+.0%}")
    families = {
        s["key"].split("#")[0]
        for runs in (b_runs, h_runs)
        for fx in fixtures
        for r in runs[fx]
        for c in r["calls"]
        for s in c.get("segments", [])
        if s["key"].startswith("tool_result:")
    }
    for fam in sorted(families):

        def tokens(r: dict[str, Any], fam: str = fam) -> float:
            return sum(s["tokens"] for c in r["calls"] for s in c.get("segments", []) if s["key"].split("#")[0] == fam)

        iv = changed(per_run(b_runs, tokens), per_run(h_runs, tokens))
        if iv:
            reasons.append(f"`{fam}` tokens per run changed {iv.point:+.0%}")
    return reasons

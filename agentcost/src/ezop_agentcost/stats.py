"""Bootstrap confidence intervals and the gating rule.

The check fails only when the *whole* 95% interval lies past the threshold. Anything less is reported, never gated.

Resampling is two-level: fixtures are resampled with replacement (paired, base and head together), then each
fixture's samples are resampled within base and within head. The second level carries run-to-run noise into the
interval, so a suite with few fixtures can't produce a falsely tight interval.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import median
from typing import Callable

Samples = dict[str, list[float]]  # fixture -> per-run values

DEFAULT_ITERATIONS = 2000
DEFAULT_SEED = 20261017


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolation percentile, ``q`` in [0, 100]."""
    if not values:
        return float("nan")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q / 100
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def p50_metric(data: Samples) -> float:
    """Mean over fixtures of each fixture's median cost per run."""
    meds = [median(v) for v in data.values() if v]
    return sum(meds) / len(meds) if meds else float("nan")


def p90_metric(data: Samples) -> float:
    """90th percentile of cost per run over all runs."""
    return percentile([x for v in data.values() for x in v], 90)


def mean_metric(data: Samples) -> float:
    vals = [sum(v) / len(v) for v in data.values() if v]
    return sum(vals) / len(vals) if vals else float("nan")


@dataclass
class Interval:
    point: float
    low: float
    high: float

    def to_dict(self) -> dict[str, float]:
        return {"point": self.point, "low": self.low, "high": self.high}


def _resample(rng: random.Random, fixtures: list[str], data: Samples) -> Samples:
    out: Samples = {}
    for i, fx in enumerate(fixtures):
        vals = data[fx]
        out[f"{fx}#{i}"] = [vals[rng.randrange(len(vals))] for _ in vals]
    return out


def bootstrap_relative_change(
    base: Samples,
    head: Samples,
    metric: Callable[[Samples], float],
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = DEFAULT_SEED,
) -> Interval:
    """Interval for ``metric(head) / metric(base) - 1`` over paired fixtures."""
    fixtures = sorted(set(base) & set(head))
    b0, h0 = metric({f: base[f] for f in fixtures}), metric({f: head[f] for f in fixtures})
    point = h0 / b0 - 1 if b0 else float("inf") if h0 else 0.0
    rng = random.Random(seed)
    stats: list[float] = []
    for _ in range(iterations):
        pick = [fixtures[rng.randrange(len(fixtures))] for _ in fixtures]
        b = metric(_resample(rng, pick, base))
        h = metric(_resample(rng, pick, head))
        stats.append(h / b - 1 if b else (float("inf") if h else 0.0))
    return Interval(point, percentile(stats, 2.5), percentile(stats, 97.5))


def bootstrap_value(
    data: Samples, metric: Callable[[Samples], float], iterations: int = DEFAULT_ITERATIONS, seed: int = DEFAULT_SEED
) -> Interval:
    """Interval for ``metric(data)`` (used for absolute budgets on the head)."""
    fixtures = sorted(data)
    rng = random.Random(seed)
    stats = []
    for _ in range(iterations):
        pick = [fixtures[rng.randrange(len(fixtures))] for _ in fixtures]
        stats.append(metric(_resample(rng, pick, data)))
    return Interval(metric(data), percentile(stats, 2.5), percentile(stats, 97.5))


def bootstrap_difference(
    base: Samples,
    head: Samples,
    metric: Callable[[Samples], float],
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = DEFAULT_SEED,
) -> Interval:
    """Interval for ``metric(base) - metric(head)`` (a drop, used for pass rate)."""
    fixtures = sorted(set(base) & set(head))
    point = metric({f: base[f] for f in fixtures}) - metric({f: head[f] for f in fixtures})
    rng = random.Random(seed)
    stats = []
    for _ in range(iterations):
        pick = [fixtures[rng.randrange(len(fixtures))] for _ in fixtures]
        stats.append(metric(_resample(rng, pick, base)) - metric(_resample(rng, pick, head)))
    return Interval(point, percentile(stats, 2.5), percentile(stats, 97.5))


REGRESSION = "regression"
INCONCLUSIVE = "inconclusive"
OK = "ok"


def verdict(interval: Interval, threshold: float) -> str:
    """``regression`` if the whole interval is above the threshold, ``inconclusive`` if it straddles it."""
    if interval.low > threshold:
        return REGRESSION
    if interval.high > threshold:
        return INCONCLUSIVE
    return OK

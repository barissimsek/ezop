import random

from ezop_agentcost.stats import (
    INCONCLUSIVE,
    OK,
    REGRESSION,
    Interval,
    bootstrap_relative_change,
    mean_metric,
    p50_metric,
    percentile,
    verdict,
)


def noisy(rng, center, n=3, sd=0.05):
    return [center * (1 + rng.gauss(0, sd)) for _ in range(n)]


def suite(rng, scale, fixtures=15):
    return {f"f{i}": noisy(rng, scale * (0.1 + 0.01 * i)) for i in range(fixtures)}


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([5], 90) == 5


def test_verdict_rule():
    assert verdict(Interval(0.3, 0.2, 0.4), 0.15) == REGRESSION
    assert verdict(Interval(0.2, 0.1, 0.3), 0.15) == INCONCLUSIVE
    assert verdict(Interval(0.05, 0.0, 0.1), 0.15) == OK
    assert verdict(Interval(-0.2, -0.3, -0.1), 0.15) == OK


def test_clear_regression_gates_and_noop_does_not():
    rng = random.Random(0)
    base = suite(rng, 1.0)
    iv = bootstrap_relative_change(base, suite(rng, 1.35), p50_metric, iterations=500)
    assert verdict(iv, 0.15) == REGRESSION and iv.low < 0.35 < iv.high
    iv = bootstrap_relative_change(base, suite(rng, 1.0), p50_metric, iterations=500)
    assert verdict(iv, 0.15) == OK


def test_few_fixtures_with_noisy_samples_do_not_produce_tight_intervals():
    base = {"only": [1.0, 1.6, 0.7]}
    head = {"only": [1.2, 0.8, 1.9]}
    iv = bootstrap_relative_change(base, head, mean_metric, iterations=500)
    assert iv.high - iv.low > 0.3  # within-fixture resampling keeps the noise in the interval


def test_bootstrap_is_reproducible():
    rng = random.Random(2)
    b, h = suite(rng, 1), suite(rng, 1.1)
    assert bootstrap_relative_change(b, h, p50_metric, iterations=200) == bootstrap_relative_change(
        b, h, p50_metric, iterations=200
    )

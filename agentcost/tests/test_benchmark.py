"""The MVP acceptance test: seeded regressions against the reference agent, offline.

Each seeded change must be attributed to the expected factor with at least the expected share of the delta, and
the no-op change must not gate.
"""

import pytest

pytestmark = pytest.mark.benchmark


@pytest.fixture(scope="module")
def results():
    import benchmark

    return {sc.variant: (sc, result, value, ok) for sc, result, value, ok in benchmark.run_benchmark(samples=3)}


@pytest.mark.parametrize(
    "variant", ["full_line_items", "longer_prompt", "timestamp_top", "extra_refine", "pricier_model", "noop"]
)
def test_seeded_regression(results, variant):
    sc, result, value, ok = results[variant]
    assert ok, f"{sc.change}: expected {sc.expectation}, measured {value:.0%}"


def test_seeded_regressions_gate_and_noop_reconciles(results):
    for variant in ("full_line_items", "timestamp_top", "extra_refine", "pricier_model"):
        assert results[variant][1]["verdict"] == "regression", variant
    for _, result, _, _ in results.values():
        a = result["attribution"]
        assert abs(sum(c["value"] for c in a["contributions"]) - a["modeled_delta"]) < 1e-12
        assert abs(a["residual"]) <= 0.05 * max(abs(a["billed_delta"]), 1e-9) + 1e-9

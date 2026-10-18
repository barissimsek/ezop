"""Method checks from the spec: exact reconciliation, order invariance, determinism."""

import random

import pytest
from conftest import make_call, make_run

from ezop_agentcost.attribution import GROUPS, Factors, FamilyFactors, decompose, modeled_cost, pooled_factors, shapley
from ezop_agentcost.pricing import PriceTable

PRICES = PriceTable()


def random_factors(rng: random.Random, families: list[str]) -> Factors:
    f = Factors(
        p_in=rng.uniform(1, 5) / 1e6,
        p_cr=rng.uniform(0.1, 0.5) / 1e6,
        p_cw=rng.uniform(5, 7) / 1e6,
        p_out=rng.uniform(10, 30) / 1e6,
        O=rng.uniform(100, 1000),
        runs=3,
    )
    for fam in families:
        if rng.random() < 0.8:
            r = rng.uniform(0, 0.7)
            f.families[fam] = FamilyFactors(S=rng.uniform(10, 5000), A=rng.uniform(1, 10), R=r, W=rng.uniform(0, 1 - r))
    return f


def test_contributions_sum_exactly_to_modeled_delta():
    rng = random.Random(1)
    fams = ["system_prompt", "tool_result:a", "tool_result:b", "assistant_turn", "overhead"]
    for _ in range(50):
        b, h = random_factors(rng, fams), random_factors(rng, fams)
        contrib = decompose(b, h)
        assert sum(contrib.values()) == pytest.approx(modeled_cost(h) - modeled_cost(b), rel=1e-9, abs=1e-15)


def test_shuffling_group_order_leaves_contributions_unchanged():
    rng = random.Random(2)
    b, h = random_factors(rng, ["x", "y"]), random_factors(rng, ["x", "y"])

    def value(sel):
        S = (h if "size" in sel else b).family("x").S
        A = (h if "appearances" in sel else b).family("x").A
        p = (h if "price" in sel else b).p_in
        return S * A * p

    base = shapley(GROUPS, value)
    for _ in range(5):
        order = list(GROUPS)
        rng.shuffle(order)
        assert shapley(tuple(order), value) == pytest.approx(base)


def test_decomposition_is_deterministic():
    rng = random.Random(3)
    b, h = random_factors(rng, ["x", "y", "z"]), random_factors(rng, ["x", "y", "z"])
    assert decompose(b, h) == decompose(b, h)


def test_interaction_split_evenly():
    # Size doubles and appearances double: cost x4. The interaction term is split between the two groups.
    b = Factors(p_in=1e-6, p_cr=1e-7, p_cw=1.25e-6, p_out=0, families={"f": FamilyFactors(S=100, A=1)})
    h = Factors(p_in=1e-6, p_cr=1e-7, p_cw=1.25e-6, p_out=0, families={"f": FamilyFactors(S=200, A=2)})
    c = decompose(b, h)
    assert c[("size", "f")] == pytest.approx(c[("appearances", "f")])
    assert c[("size", "f")] + c[("appearances", "f")] == pytest.approx(300e-6)


def test_family_present_on_one_side_is_fully_attributed():
    b = Factors(p_in=1e-6, families={})
    h = Factors(p_in=1e-6, families={"tool_result:new": FamilyFactors(S=1000, A=3)})
    c = decompose(b, h)
    assert sum(v for (g, f), v in c.items() if f == "tool_result:new") == pytest.approx(3000e-6)


def test_pooled_factors_modeled_equals_billed():
    runs = []
    for i in range(3):
        calls = [
            make_call([("overhead", 300, 300, 0), ("system_prompt", 1500, 1500, 0), ("user_input", 40, 0, 0)], 30 + i),
            make_call(
                [("overhead", 310, 310, 0), ("system_prompt", 1500, 1500, 0), ("user_input", 40, 0, 0),
                 ("tool_result:lookup#1", 200 + 50 * i, 0, 0)],
                80,
            ),
        ]  # fmt: skip
        runs.append(make_run("fx", calls, sample=i))
    f = pooled_factors(runs, PRICES)
    assert modeled_cost(f) == pytest.approx(f.billed, rel=1e-9)
    assert f.family("system_prompt").A == 2 and f.family("system_prompt").R == pytest.approx(1.0)
    assert f.steps == 2

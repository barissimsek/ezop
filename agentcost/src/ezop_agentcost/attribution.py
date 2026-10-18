"""Cost model and Shapley attribution.

Each fixture's runs are reduced to five factor groups:

=============  =====  ==========================================================================
group          sym    per run
=============  =====  ==========================================================================
size           S      mean tokens per appearance, per segment family
appearances    A      appearances per run, per family (one appearance = one instance in one call)
price          P      effective input / cache-read / cache-write / output price per token
cache          C      cache-read and cache-write share of each family's tokens
output         O      output tokens per run
=============  =====  ==========================================================================

Modeled run cost is a deterministic function of the factors::

    cost = sum_f S_f * A_f * [(1 - R_f - W_f) * P_in + R_f * P_cr + W_f * P_cw] + O * P_out

The base-to-head delta is split among the groups with Shapley values over all 2^5 counterfactual mixes (head values
for a subset of groups, base values for the rest). The model is a sum of independent per-family terms, so Shapley's
additivity gives the exact per-family split for free: each term is decomposed on its own and the parts add up.
Contributions always sum to the modeled delta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from math import factorial
from typing import Any, Callable

from ezop_agentcost.pricing import PriceTable
from ezop_agentcost.segments import family_of
from ezop_agentcost.usage import Usage

GROUPS = ("size", "appearances", "price", "cache", "output")
OUTPUT_FAMILY = "(output)"


@dataclass
class FamilyFactors:
    S: float = 0.0
    A: float = 0.0
    R: float = 0.0
    W: float = 0.0
    instances: float = 0.0

    @property
    def tokens_per_run(self) -> float:
        return self.S * self.A


@dataclass
class Factors:
    families: dict[str, FamilyFactors] = field(default_factory=dict)
    p_in: float = 0.0
    p_cr: float = 0.0
    p_cw: float = 0.0
    p_out: float = 0.0
    O: float = 0.0
    steps: float = 0.0
    runs: int = 0
    billed: float = 0.0  # mean billed cost per run, from recorded usage
    models: dict[str, float] = field(default_factory=dict)  # share of input tokens by model

    def family(self, name: str) -> FamilyFactors:
        return self.families.get(name) or FamilyFactors()

    def to_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "steps": self.steps,
            "output_tokens": self.O,
            "prices_per_mtok": {
                "input": self.p_in * 1e6,
                "cache_read": self.p_cr * 1e6,
                "cache_write": self.p_cw * 1e6,
                "output": self.p_out * 1e6,
            },
            "models": self.models,
            "billed_cost": self.billed,
            "modeled_cost": modeled_cost(self),
            "families": {
                k: {"S": v.S, "A": v.A, "R": v.R, "W": v.W, "instances": v.instances}
                for k, v in sorted(self.families.items())
            },
        }


def run_billed_cost(run: dict[str, Any], prices: PriceTable) -> float:
    total = 0.0
    for call in run.get("calls") or []:
        if call.get("usage"):
            total += prices.cost(call["model"], Usage.from_dict(call["usage"]))
    return total


def pooled_factors(runs: list[dict[str, Any]], prices: PriceTable) -> Factors:
    """Pool a fixture's samples into one factor set.

    Pooling is weighted so that totals are preserved: ``S*A`` is the mean tokens per run, ``S*A*R`` the mean
    cache-read tokens per run, and modeled cost equals mean billed cost whenever every call reported usage.
    """
    tok: dict[str, float] = {}
    app: dict[str, float] = {}
    rd: dict[str, float] = {}
    wr: dict[str, float] = {}
    inst: dict[str, float] = {}
    sums: dict[str, float] = dict.fromkeys(("u", "u_cost", "r", "r_cost", "w", "w_cost", "o", "o_cost"), 0.0)
    model_tokens: dict[str, float] = {}
    steps = 0
    billed = 0.0
    n = len(runs)
    for run in runs:
        billed += run_billed_cost(run, prices)
        keys_this_run: dict[str, set[str]] = {}
        for call in run.get("calls") or []:
            if not call.get("segments"):
                continue
            steps += 1
            price = prices.get(call["model"])
            u_call = r_call = w_call = 0.0
            for s in call["segments"]:
                f = family_of(s["key"])
                tok[f] = tok.get(f, 0.0) + s["tokens"]
                app[f] = app.get(f, 0.0) + 1
                rd[f] = rd.get(f, 0.0) + s["cache_read"]
                wr[f] = wr.get(f, 0.0) + s["cache_write"]
                keys_this_run.setdefault(f, set()).add(s["key"])
                u_call += s["tokens"] - s["cache_read"] - s["cache_write"]
                r_call += s["cache_read"]
                w_call += s["cache_write"]
            usage = Usage.from_dict(call["usage"]) if call.get("usage") else None
            p = price.for_prompt(usage.total_input if usage else int(u_call + r_call + w_call))
            if usage and usage.cache_write:
                cw_price = (usage.cache_write_5m * p.cache_write_5m + usage.cache_write_1h * p.cache_write_1h) / (
                    usage.cache_write
                )
            else:
                cw_price = p.cache_write_5m
            out = usage.output if usage else 0
            sums["u"] += u_call
            sums["u_cost"] += u_call * p.input
            sums["r"] += r_call
            sums["r_cost"] += r_call * p.cache_read
            sums["w"] += w_call
            sums["w_cost"] += w_call * cw_price
            sums["o"] += out
            sums["o_cost"] += out * p.output
            model_tokens[call["model"]] = model_tokens.get(call["model"], 0.0) + u_call + r_call + w_call
        for f, keys in keys_this_run.items():
            inst[f] = inst.get(f, 0.0) + len(keys)

    factors = Factors(runs=n)
    if n == 0:
        return factors
    for f in tok:
        factors.families[f] = FamilyFactors(
            S=tok[f] / app[f] if app[f] else 0.0,
            A=app[f] / n,
            R=rd[f] / tok[f] if tok[f] else 0.0,
            W=wr[f] / tok[f] if tok[f] else 0.0,
            instances=inst.get(f, 0.0) / n,
        )
    total_model_tokens = sum(model_tokens.values())
    factors.models = {m: t / total_model_tokens for m, t in model_tokens.items()} if total_model_tokens else {}
    # Prices with no traffic behind them (no cache writes in base, say) fall back to the dominant model's list
    # price, so counterfactual mixes stay well defined.
    dominant = max(model_tokens, key=lambda m: model_tokens[m]) if model_tokens else None
    fallback = prices.get(dominant) if dominant else None

    def eff(cost_key: str, tok_key: str, attr: str) -> float:
        if sums[tok_key] > 0:
            return sums[cost_key] / sums[tok_key] / 1e6
        return getattr(fallback, attr) / 1e6 if fallback else 0.0

    factors.p_in = eff("u_cost", "u", "input")
    factors.p_cr = eff("r_cost", "r", "cache_read")
    factors.p_cw = eff("w_cost", "w", "cache_write_5m")
    factors.p_out = eff("o_cost", "o", "output")
    factors.O = sums["o"] / n
    factors.steps = steps / n
    factors.billed = billed / n
    return factors


def family_cost(ff: FamilyFactors, p_in: float, p_cr: float, p_cw: float) -> float:
    return ff.S * ff.A * ((1 - ff.R - ff.W) * p_in + ff.R * p_cr + ff.W * p_cw)


def modeled_cost(f: Factors) -> float:
    return sum(family_cost(ff, f.p_in, f.p_cr, f.p_cw) for ff in f.families.values()) + f.O * f.p_out


def shapley(players: tuple[str, ...], value: Callable[[frozenset[str]], float]) -> dict[str, float]:
    """Exact Shapley values by subset enumeration (2^n evaluations)."""
    n = len(players)
    cache: dict[frozenset[str], float] = {}

    def v(s: frozenset[str]) -> float:
        if s not in cache:
            cache[s] = value(s)
        return cache[s]

    phi = dict.fromkeys(players, 0.0)
    for i in players:
        others = tuple(p for p in players if p != i)
        for k in range(n):
            weight = factorial(k) * factorial(n - k - 1) / factorial(n)
            for subset in combinations(others, k):
                s = frozenset(subset)
                phi[i] += weight * (v(s | {i}) - v(s))
    return phi


def decompose(base: Factors, head: Factors) -> dict[tuple[str, str], float]:
    """Split ``modeled(head) - modeled(base)`` into (group, family) contributions."""
    out: dict[tuple[str, str], float] = {}
    for fam in sorted(set(base.families) | set(head.families)):
        fb, fh = base.family(fam), head.family(fam)

        def term(sel: frozenset[str], fb: FamilyFactors = fb, fh: FamilyFactors = fh) -> float:
            S = (fh if "size" in sel else fb).S
            A = (fh if "appearances" in sel else fb).A
            c = fh if "cache" in sel else fb
            p = head if "price" in sel else base
            return S * A * ((1 - c.R - c.W) * p.p_in + c.R * p.p_cr + c.W * p.p_cw)

        for group, value in shapley(GROUPS, term).items():
            if value:
                out[(group, fam)] = out.get((group, fam), 0.0) + value

    def out_term(sel: frozenset[str]) -> float:
        return (head if "output" in sel else base).O * (head if "price" in sel else base).p_out

    for group, value in shapley(GROUPS, out_term).items():
        if value:
            out[(group, OUTPUT_FAMILY)] = out.get((group, OUTPUT_FAMILY), 0.0) + value
    return out


def group_totals(contrib: dict[tuple[str, str], float]) -> dict[str, float]:
    totals: dict[str, float] = dict.fromkeys(GROUPS, 0.0)
    for (group, _), v in contrib.items():
        totals[group] += v
    return totals

"""Versioned price table.

Costs are always computed at diff time from recorded token counts, so a provider price change never shows up as a
PR regression: base and head are priced with the same table.

All prices are USD per million tokens. Override or add models in ``agentcost.yml`` under ``pricing.overrides``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from ezop_agentcost.usage import Usage

PRICE_TABLE_VERSION = "2026-10-17"


@dataclass(frozen=True)
class ModelPrice:
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float
    # Some models bill the whole request at a higher rate once the prompt exceeds a size threshold.
    long_context_threshold: int | None = None
    long_context_multiplier_input: float = 1.0
    long_context_multiplier_output: float = 1.0

    def for_prompt(self, total_input: int) -> ModelPrice:
        """Return the effective price for a request whose prompt holds ``total_input`` tokens."""
        if self.long_context_threshold is None or total_input <= self.long_context_threshold:
            return self
        mi, mo = self.long_context_multiplier_input, self.long_context_multiplier_output
        return replace(
            self,
            input=self.input * mi,
            output=self.output * mo,
            cache_read=self.cache_read * mi,
            cache_write_5m=self.cache_write_5m * mi,
            cache_write_1h=self.cache_write_1h * mi,
            long_context_threshold=None,
        )

    def cost(self, usage: Usage) -> float:
        """Billed cost of one call, in USD."""
        p = self.for_prompt(usage.total_input)
        return (
            usage.input * p.input
            + usage.cache_read * p.cache_read
            + usage.cache_write_5m * p.cache_write_5m
            + usage.cache_write_1h * p.cache_write_1h
            + usage.output * p.output
        ) / 1_000_000


def _anthropic(inp: float, out: float, cache_read: float | None = None, **kw: Any) -> ModelPrice:
    # Cache writes cost 1.25x base input for the 5-minute TTL and 2x for the 1-hour TTL.
    return ModelPrice(
        input=inp,
        output=out,
        cache_read=cache_read if cache_read is not None else inp * 0.1,
        cache_write_5m=inp * 1.25,
        cache_write_1h=inp * 2.0,
        **kw,
    )


def _openai(inp: float, cached: float | None, out: float) -> ModelPrice:
    # OpenAI caches automatically with no write premium; models without a cached rate bill cached tokens as input.
    return ModelPrice(
        input=inp,
        output=out,
        cache_read=cached if cached is not None else inp,
        cache_write_5m=inp,
        cache_write_1h=inp,
    )


BUILTIN_PRICES: dict[str, ModelPrice] = {
    # Anthropic, first-party API rates.
    "claude-fable-5-1": _anthropic(10.0, 50.0, cache_read=0.25),
    "claude-mythos-5-1": _anthropic(10.0, 50.0, cache_read=0.25),
    "claude-fable-5": _anthropic(10.0, 50.0, cache_read=1.0),
    "claude-mythos-5": _anthropic(10.0, 50.0, cache_read=1.0),
    "claude-opus-5-5": _anthropic(4.0, 20.0, cache_read=0.20),
    "claude-opus-5": _anthropic(5.0, 25.0),
    "claude-opus-4-8": _anthropic(5.0, 25.0),
    "claude-opus-4-7": _anthropic(5.0, 25.0),
    "claude-opus-4-6": _anthropic(5.0, 25.0),
    "claude-opus-4-5": _anthropic(5.0, 25.0),
    "claude-opus-4-1": _anthropic(15.0, 75.0),
    "claude-opus-4": _anthropic(15.0, 75.0),
    "claude-sonnet-5-5": _anthropic(2.0, 10.0, cache_read=0.20),
    "claude-sonnet-5": _anthropic(2.0, 10.0),
    "claude-sonnet-4-6": _anthropic(3.0, 15.0),
    "claude-sonnet-4-5": _anthropic(3.0, 15.0),
    "claude-sonnet-4": _anthropic(3.0, 15.0),
    "claude-haiku-5-5": _anthropic(
        0.10,
        0.50,
        long_context_threshold=100_000,
        long_context_multiplier_input=5.0,
        long_context_multiplier_output=5.0,
    ),
    "claude-haiku-4-5": _anthropic(1.0, 5.0),
    "claude-3-5-haiku": _anthropic(0.80, 4.0),
    # OpenAI, standard tier, short context.
    "gpt-6-astra": _openai(10.0, 1.0, 50.0),
    "gpt-6.1-sol": _openai(2.0, 0.10, 10.0),
    "gpt-6-sol": _openai(2.0, 0.20, 10.0),
    "gpt-6-luna": _openai(0.10, 0.01, 0.50),
    "gpt-5.6-sol": _openai(4.0, 0.40, 20.0),
    "gpt-5.6-terra": _openai(2.0, 0.20, 12.0),
    "gpt-5.6-luna": _openai(0.20, 0.02, 1.20),
    "gpt-5.5": _openai(5.0, 0.50, 30.0),
    "gpt-5.5-pro": _openai(30.0, None, 180.0),
    "gpt-5.4": _openai(2.50, 0.25, 15.0),
    "gpt-5.4-mini": _openai(0.75, 0.075, 4.50),
    "gpt-5.4-nano": _openai(0.20, 0.02, 1.25),
    "gpt-5.4-pro": _openai(30.0, None, 180.0),
    "gpt-5.2": _openai(1.75, 0.175, 14.0),
    "gpt-5.2-pro": _openai(21.0, None, 168.0),
    "gpt-5.1": _openai(1.25, 0.125, 10.0),
    "gpt-5": _openai(1.25, 0.125, 10.0),
    "gpt-5-mini": _openai(0.25, 0.025, 2.0),
    "gpt-5-nano": _openai(0.05, 0.005, 0.40),
    "gpt-5-pro": _openai(15.0, None, 120.0),
    "gpt-4.1": _openai(2.0, 0.50, 8.0),
    "gpt-4.1-mini": _openai(0.40, 0.10, 1.60),
    "gpt-4.1-nano": _openai(0.10, 0.025, 0.40),
    "gpt-4o": _openai(2.50, 1.25, 10.0),
    "gpt-4o-2024-05-13": _openai(5.0, None, 15.0),
    "gpt-4o-mini": _openai(0.15, 0.075, 0.60),
    "o1": _openai(15.0, 7.50, 60.0),
    "o1-pro": _openai(150.0, None, 600.0),
    "o3-pro": _openai(20.0, None, 80.0),
    "o3": _openai(2.0, 0.50, 8.0),
    "o3-mini": _openai(1.10, 0.55, 4.40),
    "o4-mini": _openai(1.10, 0.275, 4.40),
    "gpt-4-turbo": _openai(10.0, None, 30.0),
    "gpt-4": _openai(30.0, None, 60.0),
    "gpt-3.5-turbo": _openai(0.50, None, 1.50),
}

_BOUNDARY = "-@:_"


def normalize_model(model: str) -> str:
    """Strip cloud-provider prefixes such as ``us.anthropic.`` so Bedrock/Vertex ids resolve to the base model."""
    m = model.strip().lower()
    if "claude" in m:
        m = m[m.index("claude") :]
    return m


class UnknownModelError(KeyError):
    pass


class PriceTable:
    def __init__(self, overrides: dict[str, ModelPrice] | None = None, include_builtin: bool = True):
        self.prices: dict[str, ModelPrice] = dict(BUILTIN_PRICES) if include_builtin else {}
        for name, price in (overrides or {}).items():
            self.prices[normalize_model(name)] = price
        self.version = PRICE_TABLE_VERSION if include_builtin else "custom"
        if overrides:
            self.version += "+overrides"

    def lookup(self, model: str) -> ModelPrice | None:
        """Exact match first, then the longest table key that prefixes the model id at a name boundary.

        ``claude-sonnet-4-5-20250929`` resolves to ``claude-sonnet-4-5``; ``gpt-4o-mini-2024-07-18`` to ``gpt-4o-mini``.
        """
        m = normalize_model(model)
        if m in self.prices:
            return self.prices[m]
        best: str | None = None
        for key in self.prices:
            if m.startswith(key) and m[len(key)] in _BOUNDARY:
                if best is None or len(key) > len(best):
                    best = key
        return self.prices[best] if best else None

    def get(self, model: str) -> ModelPrice:
        price = self.lookup(model)
        if price is None:
            raise UnknownModelError(
                f"no price for model '{model}'. Add it under pricing.overrides in agentcost.yml, for example:\n"
                f"  pricing:\n    overrides:\n      {model}: {{input: 3.0, output: 15.0, cache_read: 0.3}}"
            )
        return price

    def cost(self, model: str, usage: Usage) -> float:
        return self.get(model).cost(usage)

    @classmethod
    def from_config(cls, cfg: Any) -> PriceTable:
        """Build from the ``pricing`` config value: ``"builtin"`` or ``{table: builtin|none, overrides: {...}}``."""
        if cfg in (None, "builtin"):
            return cls()
        if not isinstance(cfg, dict):
            raise ValueError("pricing must be 'builtin' or a mapping with 'table' and/or 'overrides'")
        table = cfg.get("table", "builtin")
        if table not in ("builtin", "none"):
            raise ValueError("pricing.table must be 'builtin' or 'none'")
        overrides: dict[str, ModelPrice] = {}
        for model, spec in (cfg.get("overrides") or {}).items():
            overrides[model] = parse_price(model, spec)
        return cls(overrides=overrides, include_builtin=table == "builtin")


def parse_price(model: str, spec: Any) -> ModelPrice:
    if not isinstance(spec, dict) or "input" not in spec or "output" not in spec:
        raise ValueError(f"pricing override for '{model}' needs at least 'input' and 'output' (USD per MTok)")
    inp = float(spec["input"])
    return ModelPrice(
        input=inp,
        output=float(spec["output"]),
        cache_read=float(spec.get("cache_read", inp * 0.1)),
        cache_write_5m=float(spec.get("cache_write", spec.get("cache_write_5m", inp * 1.25))),
        cache_write_1h=float(spec.get("cache_write_1h", inp * 2.0)),
    )

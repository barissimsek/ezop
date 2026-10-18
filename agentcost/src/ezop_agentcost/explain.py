"""Turn attribution contributions into ranked, plain-language findings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ezop_agentcost.attribution import OUTPUT_FAMILY


@dataclass
class FamilySummary:
    S: float = 0.0  # tokens per appearance
    A: float = 0.0  # appearances per run
    instances: float = 0.0

    @property
    def calls_per_instance(self) -> float:
        return self.A / self.instances if self.instances else 0.0


@dataclass
class SideSummary:
    families: dict[str, FamilySummary] = field(default_factory=dict)
    output_tokens: float = 0.0
    cache_hit_rate: float = 0.0  # cache-read share of input tokens
    cache_write_rate: float = 0.0  # cache-write share of input tokens
    steps: float = 0.0
    models: dict[str, float] = field(default_factory=dict)

    def family(self, name: str) -> FamilySummary:
        return self.families.get(name) or FamilySummary()


@dataclass
class Finding:
    kind: str  # family | cache | price | output
    subject: str
    value: float
    sentence: str
    groups: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "value": self.value,
            "sentence": self.sentence,
            "groups": self.groups,
        }


def fmt_tokens(n: float) -> str:
    if abs(n) >= 1000:
        return f"{n / 1000:.1f}K"
    return f"{n:.0f}"


def _plural(n: float, word: str) -> str:
    return f"{n:.0f} {word}" if abs(round(n) - n) < 0.05 else f"{n:.1f} {word}"


def _family_sentence(fam: str, b: FamilySummary, h: FamilySummary, size: float, app: float) -> str:
    name = f"`{fam}`"
    if b.A == 0:
        return f"{name} is new: {fmt_tokens(h.S)} tokens, sent in {_plural(h.A, 'calls')} per run"
    if h.A == 0:
        return f"{name} is gone (was {fmt_tokens(b.S)} tokens in {_plural(b.A, 'calls')} per run)"
    parts: list[str] = []
    size_matters = abs(size) >= 0.25 * abs(app) or app == 0
    app_matters = abs(app) >= 0.25 * abs(size) and abs(h.A - b.A) > 1e-9
    if size_matters:
        verb = "grew" if h.S >= b.S else "shrank"
        part = f"{name} {verb} {fmt_tokens(b.S)} → {fmt_tokens(h.S)} tokens"
        if h.calls_per_instance >= 1.5:
            part += f" and is carried through {_plural(h.calls_per_instance, 'calls')}"
        parts.append(part)
    if app_matters:
        lead = "" if parts else f"{name} "
        parts.append(f"{lead}is sent in {b.A:.1f} → {h.A:.1f} calls per run")
    return ", and ".join(parts) if parts else f"{name} changed"


def build_findings(contrib: dict[tuple[str, str], float], base: SideSummary, head: SideSummary) -> list[Finding]:
    """Group contributions into findings, ranked by absolute dollar effect."""
    fam_groups: dict[str, dict[str, float]] = {}
    cache_by_family: dict[str, float] = {}
    price_total = 0.0
    output_total = 0.0
    for (group, fam), v in contrib.items():
        if group == "price":
            price_total += v
        elif group == "cache":
            cache_by_family[fam] = cache_by_family.get(fam, 0.0) + v
        elif group == "output" or fam == OUTPUT_FAMILY:
            output_total += v
        else:
            groups = fam_groups.setdefault(fam, {})
            groups[group] = groups.get(group, 0.0) + v

    findings: list[Finding] = []
    for fam, groups in fam_groups.items():
        size, app = groups.get("size", 0.0), groups.get("appearances", 0.0)
        sentence = _family_sentence(fam, base.family(fam), head.family(fam), size, app)
        findings.append(Finding("family", fam, size + app, sentence, groups))

    cache_total = sum(cache_by_family.values())
    if cache_by_family:
        top = max(cache_by_family, key=lambda f: abs(cache_by_family[f]))
        sentence = f"cache hit rate {base.cache_hit_rate:.0%} → {head.cache_hit_rate:.0%}"
        if abs(head.cache_write_rate - base.cache_write_rate) >= 0.01:
            sentence += f", cache writes {base.cache_write_rate:.0%} → {head.cache_write_rate:.0%} of input"
        if cache_total > 0 and head.cache_hit_rate < base.cache_hit_rate and top in ("system_prompt", "tool_schemas"):
            sentence += (
                f" (cached prefix broken at `{top}`: content that changes early in the prompt invalidates the cache)"
            )
        elif cache_total < 0 and head.cache_write_rate < base.cache_write_rate:
            sentence += " (fewer cache writes; a warmer cache on one side can cause this)"
        else:
            sentence += f" (largest effect on `{top}`)"
        findings.append(Finding("cache", "cache", cache_total, sentence, {"cache": cache_total}))

    if price_total:
        bm, hm = _models(base.models), _models(head.models)
        if bm != hm:
            sentence = f"model prices: {bm} → {hm}"
        else:
            sentence = "effective token prices changed (long-context tier or cache TTL mix)"
        findings.append(Finding("price", "price", price_total, sentence, {"price": price_total}))

    if output_total:
        verb = "grew" if head.output_tokens >= base.output_tokens else "shrank"
        sentence = f"output {verb} {fmt_tokens(base.output_tokens)} → {fmt_tokens(head.output_tokens)} tokens per run"
        findings.append(Finding("output", "output", output_total, sentence, {"output": output_total}))

    findings.sort(key=lambda f: -abs(f.value))
    return findings


def _models(shares: dict[str, float]) -> str:
    if not shares:
        return "none"
    items = sorted(shares.items(), key=lambda kv: -kv[1])
    if len(items) == 1:
        return items[0][0]
    return " + ".join(f"{m} ({s:.0%})" for m, s in items[:3])

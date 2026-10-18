"""Render a diff result as a sticky PR comment (Markdown) or terminal text."""

from __future__ import annotations

import textwrap
from typing import Any

MARKER = "<!-- agentcost-report -->"

VERDICT_LABEL = {"regression": "REGRESSION", "inconclusive": "INCONCLUSIVE", "ok": "within budget"}


def money(v: float, signed: bool = False) -> str:
    a = abs(v)
    digits = 2 if a >= 1 else 3 if a >= 0.01 else 4
    s = f"${a:,.{digits}f}"
    if signed:
        return ("+" if v >= 0 else "-") + s
    return ("-" if v < 0 else "") + s


def pct(v: float) -> str:
    if v != v or v in (float("inf"), float("-inf")):
        return "n/a"
    return f"{v:+.0%}"


def _ci(iv: dict[str, float]) -> str:
    return f"(95% CI {pct(iv['low'])} to {pct(iv['high'])})"


def summary_text(d: dict[str, Any]) -> str:
    """The fixed-width summary block shared by the PR comment and the terminal."""
    if d.get("verdict") == "error":
        return f"agentcost could not compare these runs: {d.get('error')}"
    c = d["cost"]
    lines = [
        f"Cost per run   {money(c['base_p50']):>8} → {money(c['head_p50']):<8} {pct(c['p50_change']['point']):>5}  "
        f"{_ci(c['p50_change'])}  {VERDICT_LABEL[c['p50_verdict']]}",
        f"p90 cost       {money(c['base_p90']):>8} → {money(c['head_p90']):<8} {pct(c['p90_change']['point']):>5}  "
        f"{_ci(c['p90_change'])}" + (f"  {VERDICT_LABEL[c['p90_verdict']]}" if c["p90_verdict"] != "ok" else ""),
    ]
    q = d.get("quality") or {}
    if q.get("graded_fixtures"):
        state = {
            "ok": "no significant drop",
            "inconclusive": "possible drop (inconclusive)",
            "regression": "QUALITY REGRESSION",
        }[q["verdict"]]
        lines.append(f"Pass rate      {q['base_pass_rate']:>8.0%} → {q['head_pass_rate']:<8.0%}        {state}")
    lines.append(f"Steps per run  {d['steps']['base']:>8.1f} → {d['steps']['head']:<8.1f}")

    a = d["attribution"]
    lines.append("")
    direction = "increase" if a["billed_delta"] >= 0 else "decrease"
    lines.append(f"Of the {money(a['billed_delta'], signed=True)} mean {direction} per run:")
    # Hide noise: a finding must move at least 5% of the delta and 0.5% of the base cost per run.
    floor = max(0.05 * abs(a["billed_delta"]), 0.005 * abs(c["base_mean"]))
    findings = [f for f in a["findings"] if abs(f["value"]) >= floor][:3]
    if not findings:
        lines.append("   (no cost change to explain)")
    for i, f in enumerate(findings, 1):
        sentence = f["sentence"].replace("`", "")
        wrapped = textwrap.wrap(sentence, width=64) or [""]
        lines.append(f"{i}. {money(f['value'], signed=True):>8}  {wrapped[0]}")
        lines.extend(f"{'':12}{w}" for w in wrapped[1:])
    lines.append(f"Model vs. billed residual: {money(a['residual'], signed=True)}")

    for name, b in (d.get("budgets") or {}).items():
        label = "p50" if name.endswith("p50") else "p90"
        state = {"regression": "exceeded", "inconclusive": "possibly exceeded (inconclusive)", "ok": "ok"}[b["verdict"]]
        lines.append(f"Budget {label} {money(b['limit'])}/run: {state}")
    return "\n".join(lines)


def _headline(d: dict[str, Any]) -> str:
    v = d.get("verdict")
    if v == "regression":
        return "Significant cost or quality regression"
    if v == "inconclusive":
        return "Inconclusive: the interval straddles a threshold; more samples would settle it"
    if v == "error":
        return "Comparison failed"
    return "Within budget"


def render_markdown(d: dict[str, Any], title_suffix: str = "") -> str:
    n_fx = len(d.get("fixtures") or [])
    samples = d.get("samples") or "?"
    name = d.get("name") or "agent"
    out = [
        MARKER,
        f"### Agent cost report — {name} ({n_fx} fixtures × {samples} runs){title_suffix}",
        "",
        f"**{_headline(d)}**",
        "",
        "```text",
        summary_text(d),
        "```",
    ]
    if d.get("verdict") != "error":
        out += ["", "<details><summary>Details</summary>", "", *_details(d), "", "</details>"]
    return "\n".join(out) + "\n"


def _details(d: dict[str, Any]) -> list[str]:
    a = d["attribution"]
    lines = [
        "**Attribution by factor group** (sums to the modeled delta)",
        "",
        "| Group | Δ cost / run |",
        "|---|---:|",
    ]
    for g, v in a["groups"].items():
        lines.append(f"| {g} | {money(v, signed=True)} |")
    lines += ["", "**Top contributions**", "", "| Group | Segment family | Δ cost / run |", "|---|---|---:|"]
    for c in a["contributions"][:12]:
        lines.append(f"| {c['group']} | `{c['family']}` | {money(c['value'], signed=True)} |")
    lines += [
        "",
        f"Cache hit rate {a['cache_hit_rate']['base']:.0%} → {a['cache_hit_rate']['head']:.0%} · "
        f"output tokens/run {a['output_tokens']['base']:.0f} → {a['output_tokens']['head']:.0f}",
        "",
    ]
    fb, fh = d["failures"]["base"], d["failures"]["head"]
    if fb or fh:
        lines.append(f"Failed runs (excluded from cost): base {_counts(fb)} · head {_counts(fh)}")
        lines.append("")
    um = d.get("unmatched_fixtures") or {}
    if um.get("base_only") or um.get("head_only"):
        lines.append(
            f"Unpaired fixtures (not compared): base only {um.get('base_only')}, head only {um.get('head_only')}"
        )
        lines.append("")
    tc = d.get("token_counting") or {}
    lines.append(f"Token counting: {tc.get('head')}. Price table {d.get('price_table')}.")
    base_commit = (d.get("base") or {}).get("commit") or "?"
    head_commit = (d.get("head") or {}).get("commit") or "?"
    lines.append(f"Base `{base_commit[:12]}` ({d['base'].get('created_at')}) · head `{head_commit[:12]}`.")
    if d.get("baseline_note"):
        lines.append(d["baseline_note"])
    for w in d.get("warnings") or []:
        lines.append(f"> ⚠️ {w}")
    return lines


def _counts(c: dict[str, int]) -> str:
    return ", ".join(f"{n} {k}" for k, n in sorted(c.items())) or "none"

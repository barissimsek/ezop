"""``agentcost.yml`` loading and validation."""

from __future__ import annotations

import fnmatch
import glob
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ezop_agentcost.pricing import PriceTable

CONFIG_NAMES = ("agentcost.yml", "agentcost.yaml", ".agentcost.yml")


class ConfigError(Exception):
    """Invalid configuration or fixtures (exit code 2)."""


def parse_fraction(value: Any, name: str) -> float:
    """Accept ``15%``, ``"15%"``, ``0.15`` or ``15`` (read as percent when > 1)."""
    if value is None:
        raise ConfigError(f"{name} is required")
    if isinstance(value, str):
        v = value.strip()
        try:
            return float(v[:-1]) / 100 if v.endswith("%") else _as_fraction(float(v))
        except ValueError as e:
            raise ConfigError(f"{name}: cannot parse '{value}' as a percentage") from e
    if isinstance(value, (int, float)):
        return _as_fraction(float(value))
    raise ConfigError(f"{name}: expected a percentage like 15%")


def _as_fraction(v: float) -> float:
    return v / 100 if v > 1 else v


@dataclass
class AgentConfig:
    run: str
    timeout_s: float = 300
    concurrency: int = 8
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None


@dataclass
class Fixture:
    name: str
    path: Path
    input: Any
    assertion: str | None = None


@dataclass
class Config:
    root: Path
    agent: AgentConfig
    fixtures_spec: list[str]
    samples: int = 3
    assert_module: str | None = None
    max_quality_drop: float = 0.05
    cost_per_run_p50: float | None = None
    cost_per_run_p90: float | None = None
    max_regression: float = 0.15
    spend_cap_usd: float | None = None
    pricing: Any = "builtin"
    token_counts: str = "approx"
    exact_max_requests: int = 500
    proxy_port: int = 8787
    baseline: str = "cached"  # cached | fresh
    baseline_max_age_days: float = 7
    run_on_label: str | None = None
    main_branch: str = "main"
    name: str | None = None
    drift_threshold: float = 0.10
    source: Path | None = None

    def price_table(self) -> PriceTable:
        try:
            return PriceTable.from_config(self.pricing)
        except ValueError as e:
            raise ConfigError(str(e)) from e

    def display_name(self) -> str:
        return self.name or self.root.name

    def load_fixtures(self, root: Path | None = None, only: list[str] | None = None) -> list[Fixture]:
        """Resolve fixture globs relative to ``root`` (defaults to the config's directory)."""
        base = root or self.root
        paths: list[Path] = []
        for spec in self.fixtures_spec:
            matches = sorted(glob.glob(str(base / spec), recursive=True))
            paths.extend(Path(m) for m in matches if m.endswith(".json"))
        if not paths:
            raise ConfigError(f"no fixture files match {self.fixtures_spec} under {base}")
        fixtures: list[Fixture] = []
        seen: set[str] = set()
        for p in sorted(set(paths)):
            try:
                data = json.loads(p.read_text())
            except ValueError as e:
                raise ConfigError(f"fixture {p}: invalid JSON ({e})") from e
            if not isinstance(data, dict) or "input" not in data:
                raise ConfigError(f'fixture {p}: expected an object with an "input" key (and optional "assert")')
            name = str(data.get("name") or p.stem)
            if name in seen:
                raise ConfigError(f"duplicate fixture name '{name}' ({p})")
            seen.add(name)
            fixtures.append(Fixture(name=name, path=p, input=data["input"], assertion=data.get("assert")))
        if only:
            wanted = set(only)
            fixtures = [f for f in fixtures if f.name in wanted or any(fnmatch.fnmatch(f.name, w) for w in only)]
            if not fixtures:
                raise ConfigError(f"--fixtures {only} matched no fixture")
        return fixtures


def find_config(start: Path) -> Path:
    for d in (start, *start.parents):
        for name in CONFIG_NAMES:
            if (d / name).is_file():
                return d / name
    raise ConfigError(f"no agentcost.yml found in {start} or its parents (run `ezop-agentcost init` to create one)")


def load_config(path: Path | None = None) -> Config:
    path = path or find_config(Path.cwd())
    if path.is_dir():
        path = find_config(path)
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"cannot read {path}: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return parse_config(raw, path.parent.resolve(), source=path)


def parse_config(raw: dict[str, Any], root: Path, source: Path | None = None) -> Config:
    known = {
        "name", "agent", "fixtures", "samples", "quality", "budgets", "spend_cap_usd", "pricing",
        "token_counts", "proxy", "baseline", "ci",
    }  # fmt: skip
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"unknown config keys: {sorted(unknown)}")
    agent = raw.get("agent")
    if not isinstance(agent, dict) or not agent.get("run"):
        raise ConfigError("agent.run is required: the command that runs one fixture, using {fixture} and {output}")
    if "{fixture}" not in agent["run"] or "{output}" not in agent["run"]:
        raise ConfigError("agent.run must contain both {fixture} and {output} placeholders")
    fixtures = raw.get("fixtures")
    if not fixtures:
        raise ConfigError("fixtures is required: a glob (or list of globs) of fixture JSON files")
    quality = raw.get("quality") or {}
    budgets = raw.get("budgets") or {}
    proxy = raw.get("proxy") or {}
    ci = raw.get("ci") or {}
    baseline = raw.get("baseline", "cached")
    if baseline not in ("cached", "fresh"):
        raise ConfigError("baseline must be 'cached' or 'fresh'")
    token_counts = raw.get("token_counts", "approx")
    if token_counts not in ("approx", "exact"):
        raise ConfigError("token_counts must be 'approx' or 'exact'")
    samples = int(raw.get("samples", 3))
    if samples < 1:
        raise ConfigError("samples must be >= 1")

    def money(v: Any, name: str) -> float | None:
        if v is None:
            return None
        try:
            return float(str(v).lstrip("$"))
        except ValueError as e:
            raise ConfigError(f"{name}: expected a dollar amount") from e

    cfg = Config(
        root=root,
        source=source,
        name=raw.get("name"),
        agent=AgentConfig(
            run=agent["run"],
            timeout_s=float(agent.get("timeout_s", 300)),
            concurrency=max(1, int(agent.get("concurrency", 8))),
            env={str(k): str(v) for k, v in (agent.get("env") or {}).items()},
            cwd=agent.get("cwd"),
        ),
        fixtures_spec=[fixtures] if isinstance(fixtures, str) else list(fixtures),
        samples=samples,
        assert_module=quality.get("assert"),
        max_quality_drop=parse_fraction(quality.get("max_quality_drop", "5%"), "quality.max_quality_drop"),
        cost_per_run_p50=money(budgets.get("cost_per_run_p50"), "budgets.cost_per_run_p50"),
        cost_per_run_p90=money(budgets.get("cost_per_run_p90"), "budgets.cost_per_run_p90"),
        max_regression=parse_fraction(budgets.get("max_regression", "15%"), "budgets.max_regression"),
        spend_cap_usd=money(raw.get("spend_cap_usd"), "spend_cap_usd"),
        pricing=raw.get("pricing", "builtin"),
        token_counts=token_counts,
        proxy_port=int(proxy.get("port", 8787)),
        baseline=baseline,
        baseline_max_age_days=float(ci.get("baseline_max_age_days", 7)),
        run_on_label=ci.get("run_on_label"),
        main_branch=str(ci.get("main_branch", "main")),
        drift_threshold=parse_fraction(ci.get("drift_threshold", "10%"), "ci.drift_threshold"),
    )
    cfg.price_table()  # validate pricing early
    return cfg

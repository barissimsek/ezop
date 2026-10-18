"""Command-line interface.

Exit codes: 0 = within budget or inconclusive, 1 = significant regression, 2 = config or run error.
"""

from __future__ import annotations

import json
import logging
import sys
from importlib import resources
from pathlib import Path

import click

from ezop_agentcost import __version__
from ezop_agentcost.ci import compare_local, progress_printer, run_ci
from ezop_agentcost.config import Config, ConfigError, load_config
from ezop_agentcost.diff import EXIT_ERROR, DiffOptions, diff_reports
from ezop_agentcost.github import GitHubError
from ezop_agentcost.gitutil import GitError, head_sha
from ezop_agentcost.pricing import PriceTable
from ezop_agentcost.render import render_markdown, summary_text
from ezop_agentcost.runner import Variant, read_report, run_check, write_report


def _log(msg: str) -> None:
    click.echo(msg, err=True)


def _load(config: Path | None) -> Config:
    return load_config(config)


def _fixture_filter(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="ezop-agentcost")
@click.option("-v", "--verbose", is_flag=True, help="Debug logging.")
def main(verbose: bool) -> None:
    """Explain why a pull request changed what your LLM agent costs."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING, format="%(name)s: %(message)s")


config_option = click.option(
    "-c", "--config", type=click.Path(path_type=Path, exists=True), help="Path to agentcost.yml (default: search up)."
)


@main.command()
@config_option
@click.option("-o", "--out", type=click.Path(path_type=Path), default=Path(".agentcost/report.json"), show_default=True)
@click.option("-n", "--samples", type=int, help="Samples per fixture (overrides config).")
@click.option("-f", "--fixtures", "fixture_names", help="Comma-separated fixture names or globs to run.")
@click.option("--keep-payloads", type=click.Path(path_type=Path), help="Keep raw request/response JSONL in this dir.")
def run(
    config: Path | None, out: Path, samples: int | None, fixture_names: str | None, keep_payloads: Path | None
) -> None:
    """Run every fixture N times behind the recording proxy and write report.json."""
    cfg = _load(config)
    fixtures = cfg.load_fixtures(only=_fixture_filter(fixture_names))
    try:
        commit: str | None = head_sha(cfg.root)
    except GitError:
        commit = None
    reports = run_check(
        cfg,
        [Variant("head", cfg.root, commit=commit)],
        fixtures,
        samples,
        keep_payloads=keep_payloads,
        progress=progress_printer(_log),
    )
    report = reports["head"]
    write_report(report, out)
    ok = sum(1 for r in report["runs"] if r["status"] == "ok")
    _log(f"{ok}/{len(report['runs'])} runs ok, ${report['spend_usd']:.4f} spent -> {out}")
    for w in report["warnings"]:
        _log(f"warning: {w}")
    sys.exit(0 if ok else EXIT_ERROR)


@main.command()
@click.argument("base", type=click.Path(path_type=Path, exists=True))
@click.argument("head", type=click.Path(path_type=Path, exists=True))
@config_option
@click.option("--comment", type=click.Path(path_type=Path), help="Write the PR comment Markdown here.")
@click.option("--json", "json_out", type=click.Path(path_type=Path), help="Write the full diff result as JSON here.")
@click.option("--max-regression", help="Override budgets.max_regression, e.g. 15%.")
def diff(
    base: Path, head: Path, config: Path | None, comment: Path | None, json_out: Path | None, max_regression: str | None
) -> None:
    """Compare two reports: statistics, verdict, and cost attribution."""
    try:
        cfg: Config | None = _load(config)
    except ConfigError:
        if config:
            raise
        cfg = None
    opts = DiffOptions.from_config(cfg) if cfg else DiffOptions()
    if max_regression:
        from ezop_agentcost.config import parse_fraction

        opts.max_regression = parse_fraction(max_regression, "--max-regression")
    prices = cfg.price_table() if cfg else PriceTable()
    result = diff_reports(read_report(base), read_report(head), prices, opts)
    click.echo(summary_text(result))
    if comment:
        comment.write_text(render_markdown(result))
    if json_out:
        json_out.write_text(json.dumps(result, indent=1))
    sys.exit(int(result["exit_code"]))


@main.command()
@config_option
@click.option("-b", "--base", "base_ref", help="Base git ref (default: merge base of HEAD with ci.main_branch).")
@click.option("-f", "--fixtures", "fixture_names", help="Comma-separated fixture names or globs to run.")
@click.option("--out-dir", type=click.Path(path_type=Path), default=Path(".agentcost"), show_default=True)
def compare(config: Path | None, base_ref: str | None, fixture_names: str | None, out_dir: Path) -> None:
    """Run a base ref and your working tree side by side, then diff them (local dev loop)."""
    cfg = _load(config)
    sys.exit(compare_local(cfg, base_ref, out_dir, _fixture_filter(fixture_names), _log))


@main.command()
@config_option
@click.option("--mode", type=click.Choice(["auto", "pr", "baseline"]), default="auto", show_default=True)
@click.option("--out-dir", type=click.Path(path_type=Path), default=Path(".agentcost"), show_default=True)
def ci(config: Path | None, mode: str, out_dir: Path) -> None:
    """GitHub Actions entrypoint: baseline on main, paired comparison on pull requests."""
    cfg = _load(config)
    sys.exit(run_ci(cfg, mode, out_dir, _log))


TEMPLATES = {
    "agentcost.yml": "agentcost.yml",
    "fixtures/example.json": "example_fixture.json",
    "fixtures/asserts.py": "asserts.py",
    "agentcost_entry.py": "agentcost_entry.py",
    ".github/workflows/agentcost.yml": "workflow.yml",
}


@main.command()
@click.option("--dir", "target", type=click.Path(path_type=Path, file_okay=False), default=Path("."), show_default=True)
@click.option("--workflow/--no-workflow", default=True, show_default=True, help="Also write a GitHub Actions workflow.")
def init(target: Path, workflow: bool) -> None:
    """Scaffold agentcost.yml, an example fixture, an assertion file, an entrypoint wrapper, and a workflow."""
    pkg = resources.files("ezop_agentcost") / "templates"
    for dest, src in TEMPLATES.items():
        if dest.startswith(".github") and not workflow:
            continue
        path = target / dest
        if path.exists():
            _log(f"exists, skipped: {path}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((pkg / src).read_text())
        _log(f"created: {path}")
    _log(
        "\nNext steps:\n"
        "  1. Edit agentcost_entry.py to call your agent (it must read {fixture} and write {output}).\n"
        "  2. Point fixtures at seeded or pinned test data where you can (a test DB, a fixed index):\n"
        "     live tool data that drifts between runs shows up as noise.\n"
        "  3. ezop-agentcost run -n 1          # smoke test: one sample per fixture\n"
        "  4. ezop-agentcost compare           # your working tree vs. the merge base with main\n"
        "  5. Add ANTHROPIC_API_KEY / OPENAI_API_KEY as repository secrets and push the workflow."
    )


def entrypoint() -> None:
    try:
        main(standalone_mode=False)
    except click.exceptions.Exit as e:
        sys.exit(e.exit_code)
    except click.ClickException as e:
        e.show()
        sys.exit(EXIT_ERROR)
    except click.exceptions.Abort:
        sys.exit(EXIT_ERROR)
    except (ConfigError, GitError, GitHubError) as e:
        click.echo(f"ezop-agentcost: {e}", err=True)
        sys.exit(EXIT_ERROR)


if __name__ == "__main__":
    entrypoint()

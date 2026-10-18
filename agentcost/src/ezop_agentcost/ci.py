"""CI orchestration: baseline lookup, drift check, paired runs, sticky comment, GitHub outputs.

PR flow::

    head = PR head commit (explicit checkout, not GitHub's test merge)
    base = git merge-base origin/main HEAD
    cached baseline report for base exists and is fresh?
        yes -> run head only; drift check vs the cached baseline
                 drift suspected -> re-run base and head interleaved, report against that fresh pair
        no  -> run base and head interleaved
    diff -> report.json files, comment.md, sticky PR comment, exit code

Baseline flow (push to main): run the commit, write ``report.json`` for upload as ``agentcost-baseline-<sha>``.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ezop_agentcost.config import Config, ConfigError
from ezop_agentcost.diff import EXIT_ERROR, DiffOptions, diff_reports, drift_check
from ezop_agentcost.github import GitHub, GitHubError
from ezop_agentcost.gitutil import head_sha, is_merge_commit, merge_base, resolve, toplevel, worktree
from ezop_agentcost.render import render_markdown, summary_text
from ezop_agentcost.runner import Variant, read_report, run_check, write_report

Log = Callable[[str], None]


def baseline_artifact_name(sha: str) -> str:
    return f"agentcost-baseline-{sha}"


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def progress_printer(log: Log) -> Callable[[int, int, str, dict[str, Any]], None]:
    def show(done: int, total: int, variant: str, rec: dict[str, Any]) -> None:
        calls = len(rec.get("_raw") or rec.get("calls") or [])
        extra = f" ({rec['error']})" if rec.get("error") else ""
        verdict = "" if rec.get("passed") is None else (" pass" if rec["passed"] else " FAIL")
        log(
            f"[{done:>3}/{total}] {variant:<4} {rec['fixture']} s{rec['sample']}: {rec['status']}{verdict}, "
            f"{calls} calls, {rec.get('duration_s') or 0:.1f}s{extra}"
        )

    return show


def _variant_dir(cfg: Config, repo: Path, tree: Path) -> Path:
    """The config's directory inside another checkout of the same repo."""
    return tree / cfg.root.resolve().relative_to(repo.resolve())


def run_paired(
    cfg: Config, base_sha: str, head_commit: str | None, fixtures: Any, log: Log, keep_payloads: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run base (in a temporary worktree) and head (the current checkout) interleaved."""
    repo = toplevel(cfg.root)
    with worktree(repo, base_sha) as tree:
        variants = [
            Variant("base", _variant_dir(cfg, repo, tree), commit=base_sha),
            Variant("head", cfg.root, commit=head_commit),
        ]
        reports = run_check(cfg, variants, fixtures, keep_payloads=keep_payloads, progress=progress_printer(log))
    return reports["base"], reports["head"]


def _write_outputs(values: dict[str, str]) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for k, v in values.items():
            f.write(f"{k}={v}\n")


def _append_summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")


def _event() -> tuple[str, dict[str, Any]]:
    name = os.environ.get("GITHUB_EVENT_NAME", "")
    path = os.environ.get("GITHUB_EVENT_PATH")
    payload: dict[str, Any] = {}
    if path and Path(path).is_file():
        payload = json.loads(Path(path).read_text())
    return name, payload


def _github() -> GitHub | None:
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None
    return GitHub(token, repo, os.environ.get("GITHUB_API_URL", "https://api.github.com"))


def ci_baseline(cfg: Config, out_dir: Path, log: Log = _stderr) -> int:
    """Push to main: run this commit and write the report to upload as the baseline artifact."""
    sha = head_sha(cfg.root)
    fixtures = cfg.load_fixtures()
    reports = run_check(cfg, [Variant("head", cfg.root, commit=sha)], fixtures, progress=progress_printer(log))
    report = reports["head"]
    report["variant"] = "baseline"
    path = out_dir / "baseline" / "report.json"
    write_report(report, path)
    ok = sum(1 for r in report["runs"] if r["status"] == "ok")
    log(f"baseline for {sha[:12]}: {ok}/{len(report['runs'])} runs ok -> {path}")
    _write_outputs({"artifact-name": baseline_artifact_name(sha), "report-path": str(path), "verdict": "baseline"})
    return 0 if ok else EXIT_ERROR


def ci_pull_request(
    cfg: Config,
    out_dir: Path,
    payload: dict[str, Any],
    gh: GitHub | None,
    log: Log = _stderr,
) -> int:
    pr = payload.get("pull_request") or {}
    labels = {lbl.get("name") for lbl in pr.get("labels") or []}
    if cfg.run_on_label and cfg.run_on_label not in labels:
        log(f"skipping: PR does not carry the '{cfg.run_on_label}' label (ci.run_on_label)")
        _write_outputs({"verdict": "skipped"})
        return 0

    if is_merge_commit(cfg.root):
        log(
            "warning: HEAD is a merge commit. If this is GitHub's test merge, check out the PR head instead "
            "(actions/checkout with ref: ${{ github.event.pull_request.head.sha }}) so the delta holds only this PR."
        )
    head = head_sha(cfg.root)
    base = merge_base(cfg.root, cfg.main_branch)
    log(f"head {head[:12]}, merge base {base[:12]}")
    fixtures = cfg.load_fixtures()
    prices = cfg.price_table()

    cached: dict[str, Any] | None = None
    note = ""
    if cfg.baseline == "cached" and gh is not None:
        try:
            art = gh.find_artifact(baseline_artifact_name(base))
            if art is None:
                note = "no cached baseline for the merge base"
            elif (age := gh.artifact_age_days(art)) > cfg.baseline_max_age_days:
                note = f"cached baseline is {age:.1f} days old (max {cfg.baseline_max_age_days:g})"
            else:
                cached = gh.download_report(art)
                note = f"cached baseline from {cfg.main_branch} ({age:.1f} days old)"
        except GitHubError as e:
            note = f"baseline lookup failed ({e})"
    elif cfg.baseline == "fresh":
        note = "baseline: fresh (configured)"
    else:
        note = "no GitHub token; cannot look up cached baselines"

    if cached is not None:
        log(f"{note}; running head only")
        head_report = run_check(
            cfg, [Variant("head", cfg.root, commit=head)], fixtures, progress=progress_printer(log)
        )["head"]
        drift = drift_check(cached, head_report, prices, cfg.drift_threshold)
        if drift:
            log("drift check: " + "; ".join(drift) + " -> re-running base and head together")
            base_report, head_report = run_paired(cfg, base, head, fixtures, log)
            note = "fresh same-time baseline (drift check: " + "; ".join(drift) + ")"
        else:
            base_report = cached
            note = f"Baseline: {note}; drift check passed."
    else:
        log(f"{note}; running base and head interleaved")
        base_report, head_report = run_paired(cfg, base, head, fixtures, log)
        note = f"Baseline: fresh run of the merge base ({note})."

    return finish(cfg, base_report, head_report, out_dir, gh, pr.get("number"), note, log)


def finish(
    cfg: Config,
    base_report: dict[str, Any],
    head_report: dict[str, Any],
    out_dir: Path,
    gh: GitHub | None,
    pr_number: int | None,
    note: str,
    log: Log,
) -> int:
    result = diff_reports(base_report, head_report, cfg.price_table(), DiffOptions.from_config(cfg))
    result["baseline_note"] = note
    markdown = render_markdown(result)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_report(base_report, out_dir / "base.json")
    write_report(head_report, out_dir / "head.json")
    (out_dir / "diff.json").write_text(json.dumps(result, indent=1))
    (out_dir / "comment.md").write_text(markdown)
    log(summary_text(result))
    _append_summary(markdown)
    if gh is not None and pr_number:
        try:
            url = gh.upsert_comment(int(pr_number), markdown)
            log(f"PR comment: {url}")
        except GitHubError as e:
            log(f"could not post the PR comment ({e}); it is in {out_dir / 'comment.md'}")
    _write_outputs(
        {
            "verdict": result["verdict"],
            "exit-code": str(result["exit_code"]),
            "comment-path": str(out_dir / "comment.md"),
            "diff-path": str(out_dir / "diff.json"),
        }
    )
    return int(result["exit_code"])


def run_ci(cfg: Config, mode: str, out_dir: Path, log: Log = _stderr) -> int:
    event, payload = _event()
    if mode == "auto":
        if event in ("pull_request", "pull_request_target"):
            mode = "pr"
        elif event in ("push", "workflow_dispatch", "schedule"):
            mode = "baseline"
        else:
            raise ConfigError(f"cannot infer --mode from GITHUB_EVENT_NAME='{event}'; pass --mode pr or baseline")
    if mode == "baseline":
        return ci_baseline(cfg, out_dir, log)
    return ci_pull_request(cfg, out_dir, payload, _github(), log)


def compare_local(cfg: Config, base_ref: str | None, out_dir: Path, fixtures_only: list[str] | None, log: Log) -> int:
    """Developer loop: compare the working tree's HEAD with a base ref (default: merge base with main)."""
    base = resolve(cfg.root, base_ref) if base_ref else merge_base(cfg.root, cfg.main_branch, fetch=False)
    head = head_sha(cfg.root)
    log(f"comparing base {base[:12]} with the working tree at {head[:12]}")
    fixtures = cfg.load_fixtures(only=fixtures_only)
    base_report, head_report = run_paired(cfg, base, head, fixtures, log)
    note = f"Baseline: local paired run of {base_ref or 'the merge base'}."
    return finish(cfg, base_report, head_report, out_dir, None, None, note, log)


__all__ = [
    "run_ci",
    "compare_local",
    "ci_baseline",
    "ci_pull_request",
    "finish",
    "baseline_artifact_name",
    "read_report",
]

"""CI orchestration against a throwaway git repo, the mock model, and a fake GitHub."""

import io
import json
import subprocess
import textwrap
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from ezop_agentcost.ci import baseline_artifact_name, ci_baseline, ci_pull_request, compare_local
from ezop_agentcost.config import load_config
from ezop_agentcost.github import GitHub
from ezop_agentcost.render import MARKER

AGENT = textwrap.dedent(
    """
    import json, sys
    import anthropic
    args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
    task = json.load(open(args["--input"]))
    system = open("prompt.txt").read()
    client = anthropic.Anthropic(api_key="test", max_retries=0)
    messages = [{"role": "user", "content": task["message"]}]
    for _ in range(3):
        r = client.messages.create(model="claude-opus-5-5", max_tokens=50, system=system, messages=messages)
        messages += [{"role": "assistant", "content": [b.model_dump() for b in r.content]},
                     {"role": "user", "content": "continue"}]
    open(args["--output"], "w").write(json.dumps({"answer": "ok"}))
    """
)

CONFIG = """
name: tiny
agent:
  run: python agent.py --input {fixture} --output {output}
  concurrency: 4
fixtures: fixtures/*.json
samples: 2
budgets:
  max_regression: 15%
"""


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, mock_claude, monkeypatch):
    server, _ = mock_claude
    monkeypatch.setenv("AGENTCOST_ANTHROPIC_UPSTREAM", server.url)
    for var in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(var, raising=False)
    r = tmp_path / "repo"
    (r / "fixtures").mkdir(parents=True)
    (r / "agent.py").write_text(AGENT)
    (r / "agentcost.yml").write_text(CONFIG)
    (r / "prompt.txt").write_text("You are terse. " * 20)
    for i in range(4):
        (r / "fixtures" / f"f{i}.json").write_text(json.dumps({"input": {"message": f"order {1042 + i} question"}}))
    git(r, "init", "-q", "-b", "main")
    git(r, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
    return r


def commit_bigger_prompt(repo):
    git(repo, "checkout", "-qb", "feature")
    (repo / "prompt.txt").write_text("You are terse but thorough and you cite the policy. " * 200)
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "longer prompt")


class FakeGitHub:
    def __init__(self, artifacts=None, age_days=1.0):
        self.artifacts = artifacts or {}
        self.age = age_days
        self.comments = []

    def find_artifact(self, name):
        return {"name": name} if name in self.artifacts else None

    def artifact_age_days(self, art):
        return self.age

    def download_report(self, art):
        return self.artifacts[art["name"]]

    def upsert_comment(self, number, body):
        self.comments.append((number, body))
        return "https://github.example/pr/1#comment"


PR = {"pull_request": {"number": 7, "labels": []}}


def test_pr_without_cached_baseline_runs_both_sides_and_comments(repo):
    commit_bigger_prompt(repo)
    gh = FakeGitHub()
    out = repo / ".agentcost"
    code = ci_pull_request(load_config(repo / "agentcost.yml"), out, PR, gh, log=lambda m: None)
    assert code == 1  # the prompt grew ~25x: a clear regression
    diff = json.loads((out / "diff.json").read_text())
    assert diff["attribution"]["findings"][0]["subject"] == "system_prompt"
    assert "fresh run of the merge base" in diff["baseline_note"]
    assert gh.comments and gh.comments[0][0] == 7 and gh.comments[0][1].startswith(MARKER)
    assert {p.name for p in out.iterdir()} >= {"base.json", "head.json", "diff.json", "comment.md"}
    base = json.loads((out / "base.json").read_text())
    assert base["commit"] != json.loads((out / "head.json").read_text())["commit"]


def test_pr_with_fresh_cached_baseline_runs_head_only(repo, tmp_path):
    cfg = load_config(repo / "agentcost.yml")
    assert ci_baseline(cfg, tmp_path / "bl", log=lambda m: None) == 0
    cached = json.loads((tmp_path / "bl" / "baseline" / "report.json").read_text())
    sha = cached["commit"]
    git(repo, "checkout", "-qb", "feature")
    (repo / "README.md").write_text("docs only")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "docs")
    gh = FakeGitHub({baseline_artifact_name(sha): cached})
    logs = []
    code = ci_pull_request(load_config(repo / "agentcost.yml"), repo / ".agentcost", PR, gh, log=logs.append)
    assert code == 0
    diff = json.loads((repo / ".agentcost" / "diff.json").read_text())
    assert "cached baseline" in diff["baseline_note"] and "drift check passed" in diff["baseline_note"]
    assert any("running head only" in m for m in logs)


def test_stale_baseline_is_rerun(repo, tmp_path):
    cfg = load_config(repo / "agentcost.yml")
    ci_baseline(cfg, tmp_path / "bl", log=lambda m: None)
    cached = json.loads((tmp_path / "bl" / "baseline" / "report.json").read_text())
    gh = FakeGitHub({baseline_artifact_name(cached["commit"]): cached}, age_days=30)
    git(repo, "checkout", "-qb", "feature")
    logs = []
    ci_pull_request(load_config(repo / "agentcost.yml"), repo / ".agentcost", PR, gh, log=logs.append)
    assert any("days old" in m and "interleaved" in m for m in logs)


def test_run_on_label_skips_unlabeled_prs(repo):
    cfg = load_config(repo / "agentcost.yml")
    cfg.run_on_label = "agentcost"
    logs = []
    assert ci_pull_request(cfg, repo / ".agentcost", PR, FakeGitHub(), log=logs.append) == 0
    assert any("skipping" in m for m in logs)
    assert not (repo / ".agentcost").exists()


def test_compare_local_with_explicit_base(repo):
    commit_bigger_prompt(repo)
    code = compare_local(load_config(repo / "agentcost.yml"), "main", repo / ".agentcost", ["f0", "f1"], lambda m: None)
    assert code == 1
    assert json.loads((repo / ".agentcost" / "diff.json").read_text())["fixtures"] == ["f0", "f1"]


# ---------------------------------------------------------------------------------------- GitHub REST client


def test_github_client_artifacts_and_sticky_comment():
    report = {"schema_version": 1, "runs": []}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("report.json", json.dumps(report))
    created = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        path = request.url.path
        if path.endswith("/actions/artifacts"):
            return httpx.Response(200, json={"artifacts": [
                {"name": "agentcost-baseline-abc", "expired": True, "created_at": "2026-10-16T00:00:00Z",
                 "archive_download_url": "https://api.github.com/dl/old"},
                {"name": "agentcost-baseline-abc", "expired": False, "created_at": created,
                 "archive_download_url": "https://api.github.com/dl/new"},
            ]})  # fmt: skip
        if path == "/dl/new":
            return httpx.Response(200, content=buf.getvalue())
        if path.endswith("/issues/7/comments") and request.method == "GET":
            page = request.url.params["page"]
            if page == "1":
                return httpx.Response(200, json=[{"id": i, "body": "other"} for i in range(100)])
            return httpx.Response(200, json=[{"id": 555, "body": f"{MARKER}\nold"}])
        if request.method == "PATCH":
            assert path.endswith("/issues/comments/555")
            return httpx.Response(200, json={"html_url": "https://github.com/o/r/pull/7#issuecomment-555"})
        return httpx.Response(404)

    gh = GitHub("t", "o/r", client=httpx.Client(transport=httpx.MockTransport(handler)))
    art = gh.find_artifact("agentcost-baseline-abc")
    assert art["archive_download_url"].endswith("/new")
    assert 1.9 < gh.artifact_age_days(art) < 2.1
    assert gh.download_report(art) == report
    assert gh.upsert_comment(7, "body").endswith("555")
    assert ("PATCH", "/repos/o/r/issues/comments/555") in seen


def test_github_client_creates_comment_when_none_exists():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[])
        assert request.method == "POST" and json.loads(request.content)["body"] == "hello"
        return httpx.Response(201, json={"html_url": "u"})

    gh = GitHub("t", "o/r", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert gh.upsert_comment(3, "hello") == "u"


def test_ci_writes_github_outputs(repo, monkeypatch, tmp_path):
    out_file = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    ci_baseline(load_config(repo / "agentcost.yml"), tmp_path / "bl", log=lambda m: None)
    text = out_file.read_text()
    assert "artifact-name=agentcost-baseline-" in text and "verdict=baseline" in text
    assert Path(text.split("report-path=")[1].splitlines()[0]).is_file()

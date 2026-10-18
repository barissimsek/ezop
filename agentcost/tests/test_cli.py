import json
import subprocess
import sys

from conftest import make_call, make_report, make_run


def agentcost(*args, cwd=None):
    return subprocess.run([sys.executable, "-m", "ezop_agentcost.cli", *args], cwd=cwd, capture_output=True, text=True)


def report(tokens):
    runs = [
        make_run(
            f"fx{f}", [make_call([("user_input", 40, 0, 0), ("tool_result:t#1", tokens * (1 + f / 10), 0, 0)], 50)], s
        )
        for f in range(6)
        for s in range(3)
    ]
    return make_report(runs)


def test_init_scaffolds_without_overwriting(tmp_path):
    (tmp_path / "agentcost.yml").write_text("keep me")
    r = agentcost("init", "--dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "agentcost.yml").read_text() == "keep me"
    for p in ("fixtures/example.json", "fixtures/asserts.py", "agentcost_entry.py", ".github/workflows/agentcost.yml"):
        assert (tmp_path / p).is_file(), p
    assert "exists, skipped" in r.stderr


def test_init_template_config_is_valid(tmp_path):
    agentcost("init", "--dir", str(tmp_path), "--no-workflow")
    from ezop_agentcost.config import load_config

    cfg = load_config(tmp_path / "agentcost.yml")
    assert [f.name for f in cfg.load_fixtures()] == ["example"]
    assert not (tmp_path / ".github").exists()


def test_diff_command_exit_codes_and_outputs(tmp_path):
    (tmp_path / "base.json").write_text(json.dumps(report(500)))
    (tmp_path / "head.json").write_text(json.dumps(report(4000)))
    (tmp_path / "same.json").write_text(json.dumps(report(500)))
    r = agentcost("diff", "base.json", "head.json", "--comment", "c.md", "--json", "d.json", cwd=tmp_path)
    assert r.returncode == 1, r.stderr
    assert "REGRESSION" in r.stdout and (tmp_path / "c.md").is_file()
    assert json.loads((tmp_path / "d.json").read_text())["verdict"] == "regression"
    r = agentcost("diff", "base.json", "same.json", cwd=tmp_path)
    assert r.returncode == 0, r.stderr


def test_config_errors_exit_2(tmp_path):
    r = agentcost("run", cwd=tmp_path)
    assert r.returncode == 2 and "no agentcost.yml" in r.stderr
    (tmp_path / "bad.json").write_text("{}")
    r = agentcost("diff", "bad.json", "bad.json", cwd=tmp_path)
    assert r.returncode == 2 and "schema_version" in r.stderr

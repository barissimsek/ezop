# CI integrations

Ready-to-use CI integrations for agentcost, one folder per CI system.

| CI system | Folder | Status |
|---|---|---|
| GitHub Actions | [github/](github/) | composite action + example workflow |

## Any other CI system

Every integration is a thin wrapper around the CLI. To run agentcost anywhere else, the job needs four things:

1. **A checkout of the PR head with full history**, not a merge commit, so `git merge-base` works.
2. **Your agent's dependencies** installed, plus `pip install ezop-agentcost`.
3. **Provider API keys** in the environment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). Never give the job production
   credentials for systems your agent writes to: agentcost runs your real tools.
4. **A command:**

```bash
ezop-agentcost compare --base origin/main --out-dir .agentcost
```

`compare` runs the merge base and your head interleaved, then diffs them. It needs no CI-specific API. The
results land in `.agentcost/`:

| File | Use |
|---|---|
| `comment.md` | Markdown summary to post wherever your CI posts reports |
| `diff.json` | machine-readable verdict and attribution ([format](../docs/report-format.md)) |
| `base.json`, `head.json` | per-run reports |

**Exit codes:** `0` within budget or inconclusive · `1` significant regression · `2` config or run error.

Cached baselines (running only the PR head) and sticky PR comments are GitHub-specific today; see
[github/](github/).

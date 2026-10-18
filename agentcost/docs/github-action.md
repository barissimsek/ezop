# GitHub Action

agentcost ships a composite action in [`ci/github/`](../ci/github/), with an example workflow next to it. One workflow covers both modes. On pushes to `main`, the
action runs the commit and uploads its report as a baseline. On pull requests, it compares the PR head with the
merge base and posts a sticky comment.

```yaml
# .github/workflows/agentcost.yml  (ezop-agentcost init writes this)
name: agentcost

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  actions: read          # look up cached baseline artifacts
  pull-requests: write   # sticky PR comment

concurrency:
  group: agentcost-${{ github.ref }}
  cancel-in-progress: true

jobs:
  agentcost:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha || github.sha }}
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install the agent
        run: pip install -e .

      - name: Agent cost check
        uses: ezop-ai/ezop/agentcost/ci/github@main
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Two lines are essential:

- **`ref: …head.sha`.** By default, GitHub checks out a test merge of the PR with *current* main. That would mix
  other people's merged changes into the head run. agentcost warns when HEAD is a merge commit.
- **`fetch-depth: 0`.** The merge base has to be in the clone. agentcost tries to unshallow if it is not.

## Inputs and outputs

| Input | Default | |
|---|---|---|
| `config` | `agentcost.yml` | Path to the config. |
| `mode` | `auto` | `auto` picks `pr` for `pull_request` events and `baseline` for `push` / `workflow_dispatch` / `schedule`. |
| `out-dir` | `.agentcost` | Where `base.json`, `head.json`, `diff.json` and `comment.md` are written. |
| `github-token` | `github.token` | For artifact lookup and the PR comment. |
| `baseline-retention-days` | `30` | Retention for baseline artifacts. Must cover `ci.baseline_max_age_days`. |
| `install` | the action's source | pip requirement for agentcost, e.g. `ezop-agentcost==0.1.0`. |

| Output | |
|---|---|
| `verdict` | `regression`, `inconclusive`, `ok`, `baseline`, `skipped`, or `error` |
| `exit-code` | `0`, `1`, or `2` (see below) |
| `comment-path` | path to the rendered Markdown comment |

The action also uploads PR reports as the artifact `agentcost-pr-<run_id>-<attempt>`, appends the comment to the
job summary, and finishes with the check's exit code: `0` within budget or inconclusive, `1` significant
regression, `2` config or run error. Make the job a required status check if regressions should block merging.

## How baselines flow

```text
push to main @ abc123 ──► ezop-agentcost ci --mode baseline ──► artifact "agentcost-baseline-abc123"
                                                                        │
PR head @ def456, merge base abc123 ──► lookup ─────────────────────────┘
        found, ≤ 7 days old   → run head only → drift check → diff
        missing or stale      → run base (git worktree) + head interleaved → diff
        drift suspected       → re-run base + head interleaved → diff
```

A PR normally pays only for its own head run. The first PR after enabling agentcost, and any PR whose merge base
was never run on `main`, runs both sides.

## Controlling spend

A check costs roughly `fixtures × samples × cost per run`, doubled when both sides run. The defaults (15 × 3) come
to about $7 at $0.15 per run. The levers, in order:

1. **`spend_cap_usd`** is a hard stop enforced by the proxy. The check is then marked capped.
2. **`ci.run_on_label: agentcost`** runs only on PRs that carry the label. Add it when a PR touches prompts, tools,
   or models.
3. **Fewer fixtures or samples.** Use `samples: 2` with more fixtures before cutting fixtures. The bootstrap handles
   fewer samples gracefully. Fewer fixtures widen the interval more.
4. **Cheaper fixtures.** Point tools at small seeded data.
5. **Path filters.** Run only when agent code changes:

   ```yaml
   on:
     pull_request:
       paths: ["src/agent/**", "prompts/**", "agentcost.yml", "fixtures/**"]
   ```

## Forks

GitHub does not expose repository secrets to `pull_request` workflows from forks. The agent has no API key there,
so every run fails and the check exits 2. Options: require a maintainer to apply the label and use
`pull_request_target` with care (it runs untrusted code with your secrets), or run agentcost only for branches in
the main repository:

```yaml
if: github.event.pull_request.head.repo.full_name == github.repository || github.event_name == 'push'
```

## Running the same thing locally

```bash
ezop-agentcost compare                    # merge base with main vs. your working tree (uncommitted changes included)
ezop-agentcost compare --base v1.4.0      # any ref
ezop-agentcost ci --mode pr               # the CI flow; needs GITHUB_EVENT_PATH, GITHUB_TOKEN, GITHUB_REPOSITORY
```

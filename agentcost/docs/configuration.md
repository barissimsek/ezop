# Configuration reference

agentcost reads `agentcost.yml` (or `agentcost.yaml`, `.agentcost.yml`). Without `--config`, it searches the
current directory and then each parent. Relative paths resolve against the directory that holds the config file.
Unknown keys are rejected, so a typo fails loudly instead of being silently ignored.

```yaml
name: support-agent                 # shown in the PR comment title (default: the config's directory name)

agent:
  run: python -m support_agent.run --input {fixture} --output {output}
  timeout_s: 300                    # per run; the process group is killed on timeout
  concurrency: 8                    # parallel runs; keep under your provider rate limits
  env:                              # extra environment for every run
    SUPPORT_DB_URL: sqlite:///fixtures/seed.db
  cwd: services/agent               # optional, relative to the config's directory

fixtures: fixtures/*.json           # glob or list of globs; recursive ** works
samples: 3                          # runs per fixture per side

quality:
  assert: fixtures/asserts.py       # module holding the functions named by fixtures' "assert"
  max_quality_drop: 5%              # gate when the pass-rate drop's whole CI is above this

budgets:
  max_regression: 15%               # gate when the whole CI of the relative cost change is above this
  cost_per_run_p50: 0.18            # optional absolute budgets, USD per run
  cost_per_run_p90: 0.40

spend_cap_usd: 15                   # hard cap per check, enforced by the proxy

pricing: builtin                    # see "Pricing" below
token_counts: approx                # approx | exact

baseline: cached                    # cached | fresh

proxy:
  port: 8787                        # falls back to a free port if taken

ci:
  main_branch: main
  baseline_max_age_days: 7          # older cached baselines are re-run
  run_on_label: agentcost           # only run on PRs carrying this label (unset: every PR)
  drift_threshold: 10%              # drift check sensitivity for cached baselines
```

## `agent`

| Key | Default | |
|---|---|---|
| `run` | required | Command template. Must contain `{fixture}` and `{output}`; `{run_id}` is optional. Split with `shlex` and not run through a shell; use `bash -c "..."` for pipes. |
| `timeout_s` | `300` | Seconds per run. A timeout is a failed sample, not a cheap one. |
| `concurrency` | `8` | Maximum parallel runs. |
| `env` | `{}` | Extra environment variables. The proxy variables always win. |
| `cwd` | config directory | Working directory for runs, relative to the config's directory. When comparing against a base commit, the same relative path inside the base checkout is used. |

**Environment each run sees:** your CI environment, then `agent.env`, then `ANTHROPIC_BASE_URL`,
`OPENAI_BASE_URL` and `AGENTCOST_RUN_ID`. API keys come from your environment and pass through the proxy unchanged.

## Fixtures

Each fixture file is a JSON object:

```json
{
  "name": "damaged_backpack",
  "input": { "message": "My order 1042 arrived damaged. Refund?" },
  "assert": "check_answer"
}
```

| Key | |
|---|---|
| `input` | Required. Any JSON value. It is written as-is to the `{fixture}` file the agent reads. |
| `assert` | Optional. Name of a function in `quality.assert`. |
| `name` | Optional. Defaults to the file name without `.json`. Must be unique. |

`ezop-agentcost run -f damaged_*,late_delivery` runs a subset. Names and globs are both accepted.

## Assertions

```python
def check_answer(output, fixture_input):   # or check_answer(output)
    assert "1042" in output["answer"], "answer does not mention the order"
```

`output` is the parsed `{output}` file, or its text if it is not valid JSON. The function passes when it returns
`None` or `True`, and fails when it returns a falsy value or raises `AssertionError`. Any other exception also
fails, and the exception's message is recorded. Assertions run in the agentcost process, using the head tree's
assertion module for both sides, so base and head are judged by the same rules.

## Budgets and gating

Percentages accept `15%`, `"15%"`, `0.15`, or `15` (values above 1 are read as percent). Dollar values accept
`0.18` or `"$0.18"`.

The rule is the same everywhere: **gate only when the whole 95% interval is past the threshold**. When it
straddles the threshold the verdict is *inconclusive*, which exits 0 and suggests more samples.

## Pricing

```yaml
pricing: builtin                            # the versioned table shipped with agentcost

pricing:
  table: builtin                            # builtin | none
  overrides:                                # USD per million tokens
    my-finetuned-model: {input: 3.0, output: 15.0, cache_read: 0.3, cache_write: 3.75, cache_write_1h: 6.0}
    claude-opus-5-5: {input: 4.0, output: 20.0, cache_read: 0.2}   # e.g. a negotiated rate
```

Missing override fields default to: `cache_read` 0.1× input, `cache_write` 1.25× input, and `cache_write_1h` 2×
input. Model ids resolve by exact match, then by the longest table key that prefixes the id at a `-`, `@`, `:` or
`_` boundary: `claude-haiku-4-5-20251001` resolves to `claude-haiku-4-5`. Cloud prefixes such as `us.anthropic.`
are stripped. A model with no price fails the diff with exit 2 and a snippet to paste into `overrides`.

The table version is printed in every comment. Prices are applied at diff time, so updating agentcost never turns
an old baseline into a fake regression: both sides are priced by the same table.

## `token_counts`

- `approx` (default): local counts, scaled to billed totals per call. OpenAI models use their own tiktoken
  encoding.
- `exact`: also counts Claude segment texts with Anthropic's free `count_tokens` endpoint, deduplicated and capped
  at 500 requests per check. Needs `ANTHROPIC_API_KEY`.

See [how-it-works.md](how-it-works.md#token-counting-tokenspy) for what each method guarantees.

## `baseline`

- `cached` (default): on PRs, reuse the `main` report for the merge base when it exists and is fresh. A drift check
  re-runs both sides together when tool output looks different.
- `fresh`: always run base and head interleaved in the same job. This doubles spend in exchange for certainty.

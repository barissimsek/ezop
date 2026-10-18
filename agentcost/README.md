# ezop-agentcost

**Agent cost regression CI.** agentcost runs your LLM agent on a fixed set of tasks for the base and the head of a
pull request, then comments on the PR with *why* the cost changed. You get the cause, not just a total:

```text
Cost per run     $0.142 → $0.191    +34%  (95% CI +22% to +47%)  REGRESSION
p90 cost         $0.310 → $0.520    +68%  (95% CI +41% to +90%)  REGRESSION
Pass rate           91% → 92%             no significant drop
Steps per run       6.1 → 6.3

Of the +$0.049 mean increase per run:
1.  +$0.038  tool_result:lookup_order grew 2.1K → 9.4K tokens and is
            carried through 6 calls
2. +$0.0090  system_prompt grew 1.2K → 1.8K tokens
3. +$0.0020  cache hit rate 71% → 58% (cached prefix broken at
            system_prompt: content that changes early in the prompt
            invalidates the cache)
Model vs. billed residual: +$0.0000
```

It gates the build only when the whole 95% confidence interval is past your threshold. Noise is reported but never
fails a PR, which is what keeps the check switched on.

- **No code changes to your agent.** A local recording proxy captures every call from the official Anthropic and
  OpenAI Python SDKs, and anything built on them (LangGraph, the Claude Agent SDK, custom loops).
- **Statistics, not anecdotes.** It runs N fixtures × K samples, bootstraps a confidence interval, and pairs base and
  head by fixture.
- **Attribution that adds up.** The cost delta is split among segment size, appearances, model price, cache rate,
  and output using Shapley values. The parts always sum exactly to the modeled delta.
- **Quality next to cost.** Plain Python assertions per fixture, so a change that is cheaper but worse shows up on
  the same screen.

Install `ezop-agentcost` from PyPI. It provides the `ezop-agentcost` command and the `ezop_agentcost` Python package.

v0 supports Python 3.10+, the Anthropic Messages API, OpenAI Chat Completions and Responses, and GitHub Actions.

## Quickstart

```bash
pip install ezop-agentcost
cd your-agent-repo
ezop-agentcost init                     # agentcost.yml, fixtures/, asserts, entrypoint wrapper, workflow
```

**1. Give agentcost an entrypoint.** Each run is a fresh process started from `agent.run`. The agent reads its task
from `{fixture}` and writes its final answer to `{output}`:

```yaml
# agentcost.yml
agent:
  run: python -m support_agent.run --input {fixture} --output {output}
fixtures: fixtures/*.json
samples: 3
```

If your repo has no such entrypoint, edit the generated `agentcost_entry.py` to call your agent. Build provider
clients the default way (`anthropic.Anthropic()`, `openai.OpenAI()`). They read `ANTHROPIC_BASE_URL` and
`OPENAI_BASE_URL`, which agentcost points at its proxy for every run.

**2. Write fixtures.** A fixture is a JSON object with an `input` (handed to your agent as-is) and an optional
`assert` naming a function in your assertions file:

```json
{ "input": { "message": "My order 1042 arrived damaged. Refund?" }, "assert": "check_refund" }
```

```python
# fixtures/asserts.py
def check_refund(output, fixture_input):
    assert "refund" in output["answer"].lower()
```

Point tools at stable data where you can (a seeded test database, a pinned search index). Live data that changes
between runs is noise.

**3. Run it locally.**

```bash
ezop-agentcost run -n 1        # smoke test: one sample per fixture, writes .agentcost/report.json
ezop-agentcost compare         # your working tree vs. the merge base with main, side by side
```

**4. Turn on CI.** Commit the generated `.github/workflows/agentcost.yml` and add `ANTHROPIC_API_KEY` and/or
`OPENAI_API_KEY` as repository secrets. Merges to `main` store a baseline report, and each PR posts or updates one
sticky comment. See [docs/github-action.md](https://github.com/ezop-ai/ezop/blob/main/agentcost/docs/github-action.md).

## Commands

| Command | What it does |
|---|---|
| `ezop-agentcost init` | Scaffold the config, an example fixture, assertions, an entrypoint wrapper, and a workflow. |
| `ezop-agentcost run` | Run fixtures × samples behind the proxy and write `report.json`. |
| `ezop-agentcost diff BASE HEAD` | Compare two reports: statistics, verdict, attribution. `--comment` writes the PR comment. |
| `ezop-agentcost compare [--base REF]` | Run a base ref (default: merge base with main) and your working tree interleaved, then diff. |
| `ezop-agentcost ci` | The GitHub Actions entrypoint: baseline on `main`, paired comparison on pull requests. |

**Exit codes:** `0` within budget or inconclusive · `1` significant regression · `2` config or run error.

## How it works, in one screen

```text
agent subprocess ──► 127.0.0.1:8787/run/<run_id>/anthropic ──► api.anthropic.com
                 ◄── (streams relayed chunk by chunk)       ◄──
                         │ records request, response, billed usage
                         ▼
     segments: tool_schemas · system_prompt · user_input · tool_result:<name>#n · assistant_turn#n · overhead
                         ▼
     factors per fixture: size S · appearances A · price P · cache C · output O
                         ▼
     Shapley split of Δcost over {S, A, P, C, O} · bootstrap CI · verdict · plain-language findings
```

1. **Capture.** The proxy forwards every request unchanged (your API key passes through and is never stored) and
   records the full request and response for that run.
2. **Segmentation.** Each call's prompt is split into segments with keys that stay stable across runs. Billed input
   tokens are allocated to segments by local token count, scaled to the billed total. For Claude, each cache zone
   is calibrated to the billed cache-read and cache-write counts.
3. **Cost model.** For each segment family:
   `cost = Σ_f S_f · A_f · [(1 − R_f − W_f)·P_in + R_f·P_cache_read + W_f·P_cache_write] + O · P_out`.
4. **Attribution.** All 32 base/head mixes of the five factor groups are evaluated (arithmetic only, no API
   calls), and Shapley values split the delta.
5. **Statistics.** A two-level bootstrap (fixtures, then samples within fixtures) gives 95% intervals for the change
   in median and p90 cost per run.

The full explanation is in [docs/how-it-works.md](https://github.com/ezop-ai/ezop/blob/main/agentcost/docs/how-it-works.md).

## Documentation

- [How it works](https://github.com/ezop-ai/ezop/blob/main/agentcost/docs/how-it-works.md): the proxy, segments, cost model, attribution, statistics, and the limits of each
- [Configuration reference](https://github.com/ezop-ai/ezop/blob/main/agentcost/docs/configuration.md): every `agentcost.yml` key
- [GitHub Action](https://github.com/ezop-ai/ezop/blob/main/agentcost/docs/github-action.md): workflow setup, baselines, cost control, forks
- [Report format](https://github.com/ezop-ai/ezop/blob/main/agentcost/docs/report-format.md): `report.json` and `diff.json`
- [Contributing](https://github.com/ezop-ai/ezop/blob/main/agentcost/docs/contributing.md): dev setup, tests, the seeded benchmark, adding a provider surface
- [Reference agent](https://github.com/ezop-ai/ezop/blob/main/agentcost/examples/support_agent/README.md): the demo agent and its seeded regressions

## Privacy

Everything runs inside your CI runner. Raw prompts and responses stay in memory and are dropped after
segmentation. Only the derived report (token counts per segment key, no content) is stored as a build artifact.
Pass `--keep-payloads DIR` to keep the raw JSONL for debugging.

## Limits (v0)

- Agents that bypass the base-URL variables (hard-coded endpoints, custom HTTP clients) are not captured. A run with
  zero recorded calls triggers a warning.
- Token splits between segments are approximate for Claude, because Anthropic publishes no local tokenizer. Deltas
  are more reliable than shares. `token_counts: exact` uses the free `count_tokens` endpoint to tighten them.
- Tools run live; record/replay cassettes are not in v0. A drift check re-runs the baseline when tool output looks
  different from the cached one.
- Not in v0: dashboards, production monitoring, LLM-as-judge quality, non-Python agents, CI systems other than GitHub.

## License

Apache-2.0

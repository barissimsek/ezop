# Agent Cost Regression CI — MVP Spec

Oct 17, 2026 · @Baris Simsek

## Problem and goal

The MVP must prove one claim: the tool names the correct cause of an agent cost regression on a pull request, with enough statistical confidence that engineers keep the check on.

Agent cost changes with every prompt, tool, and model edit, and existing CI tools report only totals ("cost +34%") or static estimates. Engineers cannot act on a total. They can act on "`lookup_order` output grew 7K tokens and is carried through 6 calls." That sentence is the product.

Non-goal for v0: dashboards, production monitoring, and optimization advice. The MVP is a measurement and explanation tool for one repo.

## Target user and scope

One engineer, one Python agent repo, GitHub Actions. The agent calls Anthropic or OpenAI directly or through a framework that uses their Python SDKs underneath (LangGraph, Claude Agent SDK, custom loops).

| Dimension | v0 support |
| --- | --- |
| Language | Python 3.10+ |
| Providers | Anthropic, OpenAI (Python SDKs) |
| CI | GitHub Actions |
| Agent shape | Single agent with tool loop; sub-agents work if they use the same SDKs |
| Quality signal | Plain Python assertions per fixture |

Working name: `agentcost`.

## System overview

The MVP is two CLI commands wired together by one GitHub Action: `agentcost run` produces a report, and `agentcost diff` compares two reports.

&#91;embedded content: agentcost CI flow · head run vs. cached baseline\]

Merges to main refresh the baseline, so a PR pays only for its own head run; the diff step is where statistics and attribution happen.

## Capture

Capture uses a local recording proxy: a small HTTP server that `agentcost` starts inside the CI job for the duration of the check. The agent talks to the proxy instead of the provider; the proxy forwards every request unchanged and records both the request and the response.

```text
agent  ->  localhost:8787 (recording proxy)  ->  api.anthropic.com / api.openai.com
       <-                                    <-
```

**How the agent is redirected.** For each run, `agentcost` sets environment variables the SDKs already read, with a run ID in the path:

```text
ANTHROPIC_BASE_URL=http://localhost:8787/run/<run_id>
OPENAI_BASE_URL=http://localhost:8787/run/<run_id>/v1
```

The proxy strips `/run/<run_id>`, forwards the call, and files the recording under that run. The agent needs no code changes, and parallel runs stay separate.

**Proxy responsibilities:**

1. **Route** by path to `api.anthropic.com` or `api.openai.com`.
2. **Forward faithfully:** headers (including the API key, passed through and never stored), body, status codes, and errors.
3. **Tee streams:** relay each streamed chunk to the agent immediately while assembling a copy, including the usage that arrives at the end of the stream.
4. **Record** one JSONL line per call: run ID, call order, full request (system prompt, messages, tool definitions, model, parameters), full response, billed usage (input, output, cache-read, cache-write tokens), and latency.
5. **Enforce the spend cap:** track running cost and return a clear error once the cap is hit; the check is then marked as capped.

**Provider surfaces.** Support is staged; week 1 builds two surfaces fully and smoke-tests two more to surface design risk early.

| Surface | Week 1 | v0 | Notes |
| --- | --- | --- | --- |
| Anthropic Messages API | Full | Full | Streaming and non-streaming |
| OpenAI Chat Completions | Full | Full | Streaming and non-streaming |
| OpenAI Responses API | Smoke test | Full (weeks 2–3) | With `previous_response_id`, history lives server-side; the proxy rebuilds carried context by chaining the run's recorded turns. Distinct streaming events |
| Claude Agent SDK (Claude Code CLI subprocess) | Smoke test | Capture only | Depends on the CLI honoring `ANTHROPIC_BASE_URL` through the SDK. The CLI compacts its own context and may make auxiliary calls, so attribution is limited (many `mutated` segments) |

A smoke test points a sample agent at the proxy and checks that traffic arrives and parses. A structural failure there changes the capture design, so it is cheaper to learn in week 1.

**Why full payloads.** Attribution must see what is in each call's context. OpenTelemetry GenAI spans often omit message content by default, so v0 does not depend on them.

**Privacy.** Everything stays in the CI runner. Only the derived report is stored as a build artifact; raw payloads are discarded unless `--keep-payloads` is set.

**Build, not reuse.** The proxy is written in-house: a few hundred lines of Python (Starlette + httpx); streaming is the only part that needs real care. General LLM gateways add weight and may translate between provider formats, which risks inexact capture. Generic proxies would need the same LLM-specific logic written as plugins. The proxy is also where tool cassettes, model-swap replay, and production capture will live later.

**Limits.** Agents that ignore the base-URL variables (hard-coded endpoints, custom HTTP clients) are not captured; a run with zero recorded calls triggers a warning. The proxy cannot see which line of code made a call, so file-and-line attribution waits for an optional SDK-patching mode.

## Run model

Each check runs N fixtures × K samples; defaults are 15 × 3 = 45 agent runs.

- **Fixture:** a JSON input plus an optional assertion function.
- **Samples:** repeated runs of the same fixture, so variance is measured rather than guessed.
- **Baseline:** a report keyed by the commit SHA of the PR's merge base with `main`. Every merge to main stores its report as a CI artifact under that commit's SHA. A PR whose merge-base report exists and is under 7 days old runs only its head; otherwise the job also runs the merge-base commit (see Baseline pairing).
- **Tools:** run live. Record/replay cassettes are out of scope for v0; K samples absorb tool variance.
- **Cost controls:** `run-on-label` mode (run only when a PR carries a label), fixture subsets, and a hard spend cap per check.

**Baseline pairing.** The comparison is always merge base vs. PR head, so the delta contains only the PR's own changes, not merges that landed on main after the branch was cut.

- **Checkout:** the job checks out the PR head commit explicitly. GitHub's default checkout for pull requests is a test merge with current main, which would mix other people's changes into the head run.
- **Lookup:** the baseline is the report for `git merge-base origin/main HEAD`. If it is missing (commit never run, artifact expired, label-only runs), the job runs that commit itself.
- **Freshness:** baselines older than 7 days are re-run, because provider-side model updates can change behavior at the same commit.
- **Pricing:** costs are computed at diff time from recorded tokens with the current price table, so a provider price change never appears as a PR regression.
- **Trade-off:** interactions between the PR and newer main changes are not caught here; the next post-merge baseline on main captures the combined effect.

**Drift control.** Tools return live data, so a cached baseline and today's head run can differ because the world changed, not the code. Samples absorb noise within one job, not drift between days. Drift cannot be told apart from a real change by inspecting the data (seeded test 1 is the same tool call returning more), so the fix is timing:

- **Drift check before reporting:** if any `tool_result` family's size, or the step count, differs significantly from the cached baseline, the job re-runs the merge-base commit now and reports against that fresh baseline. Base and head runs are interleaved so both see the same tool data and provider state. Any reported tool-related regression therefore comes from a same-time pair, and spend doubles only on PRs that show a suspicious change.
- **Strict mode:** `baseline: fresh` always runs base and head in the same job, for teams that prefer certainty over cost.
- **Stable test data:** fixtures should point tools at seeded or pinned data (a test database, a fixed search index) where possible; `agentcost init` recommends this.
- **Long-term fix:** tool record/replay cassettes remove drift entirely; they stay deferred for setup cost.

**How the agent is run.** Each run is a separate subprocess started from a command template the user provides; nothing is imported into `agentcost` itself.

```yaml
agent:
  run: python -m support_agent.run --input {fixture} --output {output}
  timeout_s: 300
  concurrency: 8
```

For each fixture × sample, `agentcost`:

1. Assigns a run ID and writes the fixture to a temp file.
2. Launches the command with `{fixture}` and `{output}` filled in, and the base-URL variables pointing at the recording proxy (see Capture).
3. Waits for the process to exit, up to `timeout_s`; kills it on timeout.
4. Reads the output file and runs the fixture's assertion on it.
5. Records the run: calls, tokens, cost, pass/fail, duration, and exit status.

**Execution rules:**

- **Entrypoint contract:** the agent reads its input from the `{fixture}` path and writes its final answer to `{output}`. Repos without such an entrypoint add a short wrapper script; `agentcost init` generates a template.
- **Isolation:** a fresh process per run, so no state (caches, globals, connections) leaks between runs.
- **Concurrency:** up to `concurrency` runs in parallel, kept under provider rate limits.
- **Environment:** tools run live, so CI must supply what the agent needs (API keys, tool credentials, test data). This is the main setup cost.
- **Failures:** a crash or timeout counts as a failed sample and is reported separately, so a broken agent never looks like a cheap one.
- **Deferred:** an in-process mode that imports a `module:function` entrypoint and captures by SDK patching. It is faster and gives call sites, but is Python-only and risks state leaking between runs.

**Side-effect safety.** `agentcost` must never cause real-world actions, and the proxy cannot prevent them: tools run inside the agent's process, so a tool call executes before any LLM traffic reaches the proxy. Safety therefore comes from the environment the agent runs in, and setup requires it:

- **Non-production credentials only.** CI supplies staging or sandbox credentials; read-only tools then run against test data.
- **Stubbed write tools.** Every run sets `AGENTCOST_RUN=1`. Agents use it to swap side-effecting tools (send email, issue refund, create ticket) for stubs that return a realistic success response. Stubs change tool output identically on both branches, so cost deltas stay valid.
- **Setup check.** `agentcost init` asks the developer to list write tools and confirm they are stubbed or sandboxed before the first run.
- **Long-term fix:** tool record/replay cassettes remove side effects and drift together; they need a hook into the tool layer and stay deferred.

This is the main adoption constraint: agents with write tools and no staging environment cannot be onboarded in 30 minutes. Early adopters are likely teams with mostly read-only agents or existing staging-based evals.

## Statistics and gating rule

The check fails only when the whole 95% confidence interval lies past the regression threshold. Anything less is reported, never gated. This rule is what keeps the check from being muted.

1. Pair runs by fixture; take the median cost per fixture for base and head.
2. Compute the relative change in median and p90 cost per run across fixtures.
3. Bootstrap (resample fixtures, 2,000 iterations) a 95% interval for each change.
4. Verdict:
   - Interval entirely above `max_regression` → **regression** (exit 1)
   - Interval spans the threshold → **inconclusive** (reported, exit 0, suggests more samples)
   - Otherwise → **within budget** (exit 0)

Absolute budgets (`cost_per_run_p50`, `cost_per_run_p90`) are checked against the head interval's lower bound, using the same rule.

## Attribution engine

The engine reduces each run to a small set of cost factors, then splits the base-to-head delta among them with Shapley values, so the parts sum exactly and no factor order is assumed.

**Segments.** Each LLM call's input is divided into segments with stable keys:

| Segment key | Content |
| --- | --- |
| `system_prompt` | System message |
| `tool_schemas` | Tool definitions sent with the call |
| `user_input` | The fixture's task input |
| `tool_result:<name>#<n>` | The n-th result of a named tool, for example `tool_result:lookup_order#1` in a support agent |
| `assistant_turn#<n>` | Prior model output carried forward |
| `mutated` | Content a framework summarized or truncated, which cannot be matched |
| `overhead` | Framing tokens the provider adds around content |

Billed input tokens are allocated to segments by local token count, scaled so segments sum exactly to each call's billed input. Cache-read and cache-write tokens are assigned to the prefix segments they cover.

**Token counting accuracy.** Exact per-segment counts are not available offline for Claude: Anthropic publishes no local tokenizer, and tokenizers differ between model generations. Scaling to billed totals keeps each call's sum exact, but the split between segments can be off. v0 handles this explicitly:

- **Default:** approximate local counts, scaled per call to billed input. Deltas suffer less than shares: the same text gets the same estimate on both branches, so a segment's change is measured consistently; the error concentrates in comparing shares across segment types.
- **OpenAI models:** exact offline counts with the model's published encoding.
- **Exact mode** (`token_counts: exact`): uses Anthropic's [token counting endpoint](https://platform.claude.com/docs/build-with-claude/token-counting), which is free and rate-limited separately from message creation. Counting cumulative prefixes at segment boundaries gives each segment's tokens as a difference. To stay under rate limits, it is applied to the top contributors only, with identical prefixes deduplicated. Anthropic documents these counts as estimates too, so exact mode tightens the split rather than guaranteeing it.
- **Overhead:** framing tokens the provider adds (role markers, tool-schema formatting) go to an `overhead` segment rather than being spread across content segments.
- **Disclosure:** every report states which counting method was used.

**Cost model.** Segments are grouped into families (all `tool_result:lookup_order#*` instances form one family). Each run is reduced to five factor groups:

| Factor group | Symbol | Per run |
| --- | --- | --- |
| Segment sizes | S | Mean tokens per instance, per family |
| Appearances | A | Number of calls carrying each family; total step count |
| Model prices | P | Input, output, cache-read, cache-write price per token |
| Cache rates | C | Cache-read share of each family's tokens |
| Output | O | Output tokens per run |

Modeled run cost is a deterministic function of these:

```latex
\text{cost} = \sum_{f} S_f \, A_f \, \big[(1 - C_f)\,P_{\text{in}} + C_f\,P_{\text{cache}}\big] + O \, P_{\text{out}}
```

**Decomposition method (fixed).**

1. **Average per fixture.** For each fixture, average each factor across its K samples, separately for base and head. Attribution uses means because means are additive; gating keeps medians (see Statistics).
2. **Evaluate counterfactuals.** For each of the 2^5 = 32 subsets of factor groups, compute modeled cost with that subset taken from head and the rest from base. This is arithmetic on recorded data, with no API calls.
3. **Shapley-average.** Each group's contribution is its marginal effect averaged over all orders of applying the five groups. Contributions sum exactly to the modeled delta, and interaction effects (a bigger segment carried through more steps) are split evenly between the groups involved.
4. **Split within groups.** The segment-size and appearance contributions are divided among segment families by the Owen value (Shapley within the group, holding the group total). v0 may use a proportional split as an approximation, since families rarely interact with each other.
5. **Average across fixtures** to get the reported per-run contributions; linearity keeps the sum exact.

**Residual.** Contributions always reconcile with the modeled delta. The reported residual is the gap between modeled and actually billed cost (retries, unmodeled overhead). A residual above 5% of the delta flags the cost model, not the attribution.

**Explain.** The top three contributions become plain sentences, for example: "`tool_result:lookup_order` grew 2.1K → 9.4K tokens and is carried through 6 subsequent calls (+$0.038/run)." When an interaction is large, the sentence names both causes. Stretch goal: link a tool segment to the file and line of its tool function.

**Matching across runs.** Base and head must be expressed in the same factor space before decomposition. v0 matches segment instances by family and ordinal; a family present in only one branch enters with zero size on the other side, so its full cost is attributed rather than dropped.

## Quality pairing

Every report shows pass rate next to cost, so a cheaper-but-worse change is visible on the same screen.

- A fixture may name an assertion: a Python function that receives the agent's final output and returns pass or fail.
- Pass rate is compared base vs. head with the same fixture pairing; a drop above `max_quality_drop` is flagged even when cost falls.
- LLM-as-judge scoring is out of scope for v0: it adds cost, noise, and a second model to trust.

## Outputs

The check produces three things: a sticky PR comment, a machine-readable `report.json`, and an exit code.

**PR comment** (one comment per PR, updated on each push):

```markdown
Agent cost report — support-agent (15 fixtures × 3 runs)

Cost per run   $0.142 → $0.191   +34%  (95% CI +22% to +47%)  REGRESSION
p90 cost       $0.31  → $0.52    +68%
Pass rate      91% → 92%         no significant change
Steps per run  6.1 → 6.3

Of the +$0.049 mean increase:
1. +$0.038  tool_result:lookup_order grew 2.1K → 9.4K tokens,
            carried through 6 subsequent calls
2. +$0.009  system_prompt +640 tokens, sent in every call
3. +$0.002  cache hit rate 71% → 58% (dynamic content before static prefix)
Model vs. billed residual: +$0.000

Budget: $0.18/run exceeded
```

**Exit codes:** 0 = within budget or inconclusive · 1 = significant regression · 2 = config or run error.

**Config** (`agentcost.yml`):

```yaml
agent:
  run: python -m support_agent.run --input {fixture} --output {output}
fixtures: fixtures/support/*.json
samples: 3
quality:
  assert: fixtures/support/asserts.py
  max_quality_drop: 5%
budgets:
  cost_per_run_p50: 0.18
  cost_per_run_p90: 0.40
  max_regression: 15%
spend_cap_usd: 15
pricing: builtin   # versioned price table, overridable per model
```

## Out of scope for v0

Each item below is valuable, but none is needed to prove the core claim.

| Deferred | Why it waits |
| --- | --- |
| Static cost linting (no agent run) | Cheap to add later; doesn't prove attribution |
| Tool record/replay cassettes | Setup friction; samples absorb variance for now |
| Production traces and post-deploy diff | The commercial layer, not the CI wedge |
| Hosted baselines, dashboards, org views | Needs a server; artifacts suffice for one repo |
| LLM-as-judge quality | Adds cost and noise |
| Model-swap counterfactuals | Replay validity is its own hard problem |
| Non-Python agents, non-GitHub CI | Expand after design partners validate |

## Acceptance test and success criteria

The MVP is done when the Shapley attribution assigns each seeded regression's expected share to the expected factor, stays quiet on a no-op change across 10 reruns spread over at least 3 days against a cached baseline, and keeps the model-vs-billed residual under 5%. The share thresholds below are initial values, to be tuned after the first benchmark runs.

**Reference agent:** a support-style agent with about 5 tools and a refinement loop. It is open source and doubles as the demo and the README walkthrough.

**Seeded-regression PRs:**

| # | Seeded change | Expected attribution (share of mean delta) |
| --- | --- | --- |
| 1 | A tool returns full `line_items`, output 4× larger | Segment size of `tool_result:lookup_order` ≥ 80% |
| 2 | System prompt grows by 600 tokens | Segment size of `system_prompt` ≥ 90% |
| 3 | Timestamp moved to the top of the prompt | Cache rates ≥ 80% |
| 4 | One extra refinement iteration | Appearances (step count) ≥ 50%; output and the carried `assistant_turn` account for most of the rest |
| 5 | Model swapped to a pricier tier | Model prices ≥ 90% |
| 6 | No-op refactor | No significant change; no gate |

**Method checks** (unit tests on recorded reports, no API calls):

- Contributions sum to the modeled delta exactly, to floating-point tolerance.
- Shuffling the internal order of factor groups leaves every contribution unchanged.
- Re-running the decomposition on the same recorded reports gives identical output.

**Adoption criteria:**

- [ ] Install to first PR comment in under 30 minutes on a fresh repo
- [ ] 5 external repos run it for 2+ weeks without disabling it
- [ ] At least one user fixes a real regression because of the comment

## Build plan

One engineer, about 6 weeks, in this order:

1. **Week 1 — capture.** Recording proxy for Anthropic Messages and OpenAI Chat Completions (streaming included), smoke tests for the Responses API and Claude Agent SDK, subprocess runner, `report.json`; reference agent built.
2. **Week 2 — attribution core.** Segmentation, token allocation, carried-cost math, reconciliation check.
3. **Week 3 — diff.** Delta decomposition, bootstrap statistics, plain-language explanations; Responses API support with server-side history reconstruction.
4. **Week 4 — CI.** PR comment, GitHub Action, merge-base baseline lookup with fallback run, spend cap.
5. **Week 5 — proof.** Seeded benchmark passing; README built around it.
6. **Week 6 — design partners.** Install on external repos; fix what breaks on real agents.

The seeded benchmark (week 1 agent, week 5 gate) runs in the project's own CI from week 3 onward, so attribution regressions are caught as the engine evolves.

## Risks and open questions

The biggest technical risk is matching segments across runs that take different paths; the biggest adoption risk is CI spend.

| Risk | Impact | Mitigation in v0 |
| --- | --- | --- |
| Segment matching across divergent runs | Wrong attribution | Key family + ordinal; unmatched cost goes to step count; benchmark catches errors |
| CI spend (\~$7 per PR at 45 runs × $0.15) | Teams disable the check | Baseline cached from main, `run-on-label`, fixture subsets, spend cap |
| Frameworks summarize or truncate history | Segments mutate | Detect and bucket as `mutated` rather than guess |
| Local token counts differ from billed usage | Allocation drift | Scale local counts to billed totals per call |
| Provider price changes | Stale costs | Versioned price table with overrides |
| Incumbents add cost gates (Braintrust, promptfoo) | Category pressure | Lead with attribution, which totals-based gates lack |
| Proxy mishandles streamed responses | Agent sees delays or broken streams; usage missed | Prototype the proxy first against both SDKs, streaming and non-streaming |
| Live tool data drifts between baseline and head runs | False regressions blamed on tool results; no-op gate fires | Drift check triggers a same-time base rerun; strict mode; stable test data |
| Agent tools write to production systems during CI runs | Real-world side effects (emails, refunds) multiplied across runs | Non-production credentials only; write tools stubbed via AGENTCOST\_RUN; init-time confirmation |

**Open questions:**

- Should samples adapt (run more when the interval straddles the threshold)?
- Is `run-on-label` the right default, or should every PR run?
- How should v0 handle agents that ignore the base-URL variables (for example, a client with a hard-coded endpoint)?

## Competitive context

No current tool explains why an agent PR changed cost; existing tools report totals, static estimates, or structural changes.

| Tool | What it does on a PR | Gap vs. this MVP |
| --- | --- | --- |
| [Braintrust eval-action](https://www.braintrust.dev/learn/ci-cd/v0) | Runs evals, comments scores and cost per experiment | Gates on quality; cost is a column, not explained |
| [promptfoo action](https://medium.com/@alexrodriguesj/testing-llm-prompts-like-code-regression-evals-in-ci-cd-with-promptfoo-5242b4dcb9be) | Before/after prompt comparison; cost-per-call assertion | Prompt-level, not full agent runs |
| [costdiff](https://pypi.org/project/inferenceci/) | Runs scenarios, diffs total cost/tokens/calls vs. main | No root cause, no statistics |
| [tracediff](https://pypi.org/project/tracediff/) | Structural trajectory diff with cost metric | Structural ("calls search twice"), no token provenance |
| [tokentoll](https://pypi.org/project/tokentoll/) | Static AST scan of LLM calls, "Infracost for LLM spend" | Estimates; blind to agent loops and context growth |

## Sources

- [Braintrust — CI/CD](https://www.braintrust.dev/learn/ci-cd/v0)
- [Testing LLM prompts with promptfoo](https://medium.com/@alexrodriguesj/testing-llm-prompts-like-code-regression-evals-in-ci-cd-with-promptfoo-5242b4dcb9be)
- [costdiff on PyPI](https://pypi.org/project/inferenceci/)
- [tracediff on PyPI](https://pypi.org/project/tracediff/)
- [tokentoll on PyPI](https://pypi.org/project/tokentoll/)

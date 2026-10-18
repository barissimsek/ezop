# How agentcost works

This page is for developers who want to trust the numbers in the PR comment, or change the code that produces
them. Each section names the module that implements it.

```text
 run model          capture             segmentation          cost model + attribution        statistics
 (runner.py)  ──►   (proxy.py,    ──►   (segments.py,   ──►   (attribution.py,          ──►   (stats.py,
                     sse.py)             tokens.py)            explain.py)                     diff.py)
```

## 1. Run model (`runner.py`)

A check runs **N fixtures × K samples** per side (default 15 × 3 = 45 runs). Each run:

1. gets a run id such as `head-damaged_backpack-s2-4f1607`
2. writes the fixture's `input` to a temp file
3. starts `agent.run` as a fresh subprocess, with `{fixture}`, `{output}` and `{run_id}` filled in, and the
   environment pointing the SDKs at the proxy
4. waits up to `timeout_s` and kills the whole process group on timeout
5. reads `{output}` (JSON if it parses, otherwise text) and runs the fixture's assertion
6. collects the run's recorded calls from the proxy

A fresh process per run means no caches, globals or connections leak between runs. Nothing from your agent is
imported into agentcost.

**Interleaving.** When base and head run in the same job, jobs are queued sample-major, then by fixture, with the
two variants innermost: `(s1, f1, base) (s1, f1, head) (s1, f2, base) …`. Both sides of each pair run at almost
the same moment, against the same tool data and provider state.

**Failures.** A crash, timeout, missing output file, or spend-cap hit marks the run as failed. Failed runs are
excluded from cost statistics and reported separately, so a broken agent never looks cheap. An assertion failure
is not a run failure. The run counts toward cost, with `passed: false`.

The command template is split with `shlex`, not run through a shell. For pipes or `&&`, use
`bash -c "..."`.

## 2. Capture (`proxy.py`, `sse.py`)

agentcost starts a Starlette server on `127.0.0.1:8787` (or a free port if that one is taken) for the duration of
the check. Each run gets:

```text
ANTHROPIC_BASE_URL=http://127.0.0.1:8787/run/<run_id>/anthropic
OPENAI_BASE_URL=http://127.0.0.1:8787/run/<run_id>/openai/v1
AGENTCOST_RUN_ID=<run_id>
```

Both official SDKs read these variables. The provider segment in the path makes routing unambiguous, since both
providers' APIs live under `/v1/`, and the run id keeps parallel runs apart.

**Forwarding.** Method, path, query, headers (including the API key) and body are forwarded unchanged. Hop-by-hop
headers are dropped, and `accept-encoding: identity` is requested so bodies can be parsed. Status codes and error
bodies come back unchanged. If `ANTHROPIC_BASE_URL` or `OPENAI_BASE_URL` was already set (a corporate gateway, for
example), the proxy forwards to that address instead of the public API. `AGENTCOST_ANTHROPIC_UPSTREAM` and
`AGENTCOST_OPENAI_UPSTREAM` override both.

**Recorded surfaces.** `POST /v1/messages`, `POST /v1/chat/completions`, and `POST /v1/responses`. Everything else
(model lists, `count_tokens`, file uploads) is forwarded without being recorded.

**Streams.** Events are relayed to the agent as they arrive, split at event boundaries so each event's raw bytes go
through exactly as sent. A copy goes to an assembler that rebuilds the full response:

| Surface | Where usage comes from |
|---|---|
| Anthropic Messages | `message_start.message.usage`, then cumulative `message_delta.usage` (later non-null values win) |
| OpenAI Chat Completions | the final usage-only chunk. Streams include it only when asked, so the proxy sets `stream_options.include_usage` and hides that extra chunk from an agent that did not request it |
| OpenAI Responses | the `response` object in `response.completed` / `response.incomplete` / `response.failed` |

**Spend cap.** After each call, the proxy adds its cost to a running total, using the price table (models missing
from the table are counted at a deliberately high fallback price). Once the total reaches `spend_cap_usd`, further
calls get an HTTP 400 that says the cap was reached. The SDKs do not retry 400s. The run is marked `capped`.

**What is stored.** Recordings stay in memory and are discarded after segmentation, unless you pass
`--keep-payloads DIR` (one JSONL file per run). API keys are never written anywhere.

## 3. Segmentation (`segments.py`)

Each call's prompt is turned into an ordered list of blocks, and each block gets a key that is stable across runs:

| Key | Content | Identity |
|---|---|---|
| `tool_schemas` | tool definitions | content hash; a second distinct set becomes `tool_schemas#2` |
| `system_prompt` | `system`, or Responses `instructions`, or a leading system/developer message | content hash |
| `system_message#n` | mid-conversation system or developer messages | content hash, then occurrence |
| `user_input` | the run's first user message (the fixture's task) | content hash |
| `user_message#n` | later user messages (refinement prompts, sub-agent tasks) | content hash, then occurrence |
| `tool_result:<name>#<n>` | the n-th distinct result of tool `<name>` in the run | `tool_use_id` / `tool_call_id` / `call_id` |
| `assistant_turn#<n>` | model output carried forward, produced by the run's n-th call | matched against recorded responses |
| `mutated` | content a framework rewrote, which can't be matched | — |
| `overhead` | estimated framing tokens | — |

A **family** is a key without its `#n` suffix. Attribution works on families. Instances only tell the
explanation how many calls each instance is carried through.

**Matching carried context.** Every assistant message in a request is canonicalized: text, tool calls with JSON
arguments sorted, thinking text, with `cache_control` and citations ignored. It is then looked up among the
responses recorded *earlier in the same run*. A match becomes `assistant_turn#<ordinal of the producing call>`; no
match becomes `mutated`. Tool results are keyed by their tool-call id. The tool name comes from the assistant tool
call that requested it. If a result's content later changes under the same id (a framework summarized or truncated
it), that appearance becomes `mutated`. agentcost reports such content as `mutated` rather than guess at it.

**Responses API chains.** With `previous_response_id`, the conversation lives on the server. agentcost rebuilds
it by walking the run's recorded calls: the previous call's context, plus its output items, plus this call's
input. If the chain points at a response this run never recorded, the call is flagged `unresolved_context`, local
counts are kept as they are, and the remaining billed tokens become `mutated`.

**Repeats.** Identical user or system messages at different positions in one request are separate instances. The
same refinement prompt sent twice is two appearances, not one appearance of double size.

### Allocating billed tokens

Billed usage gives each call's exact totals (uncached input, cache read, cache write, output), but not how they
split across segments. agentcost:

1. counts each block locally (see *Token counting* below)
2. inserts estimated framing as positioned `overhead` entries: a request preamble first (plus about 300 tokens of
   tool-use system prompt for Anthropic calls with tools), then a few role-marker tokens before each message block
3. scales the local counts so they sum exactly to the billed input
4. assigns cache-read tokens to the leading segments and cache-write tokens to the segments right after them

**Cache-zone calibration (Anthropic).** Claude's cache reads and writes end at cache breakpoints, which sit at
block boundaries. So the billed `cache_read` is an exact count for the segments it covers, and `cache_read +
cache_write` for those up to the last breakpoint. agentcost picks the segment boundary that fits each total best,
meaning the one needing the least *differential* scaling on its two sides. It then scales each zone separately.
This keeps tokenizer error in the uncached tail (a large JSON tool result, say) from shifting tokens in or out of
the cached system prompt. If no boundary fits within 3×, one uniform scale is used. OpenAI caches in fixed-size
increments, not at block boundaries, so OpenAI calls always get one uniform scale.

Calls that reported no usage (an interrupted stream, for example) use the local counts and are flagged
`estimated`.

### Token counting (`tokens.py`)

| Method | Used for | Accuracy |
|---|---|---|
| `openai` | OpenAI models: the model's own tiktoken encoding | exact content counts |
| `approx` | Claude models: tiktoken `o200k_base` as a stand-in | approximate; Anthropic publishes no local tokenizer |
| `heuristic` | anything, when tiktoken can't load | rough |
| `anthropic-count-tokens` | Claude, with `token_counts: exact` | the official estimate, per unique segment text |

Scaling to billed totals keeps every call's *sum* exact; only the *split* between segments depends on these
counts. Deltas suffer less than shares, because the same text gets the same estimate on both sides. Exact mode
counts each unique segment text once with the free `count_tokens` endpoint (rate-limited separately from message
creation), as a one-message prompt minus a one-character baseline. The largest texts go first, and anything past
500 requests keeps its approximate count. Every report says which methods it used.

## 4. Cost model (`attribution.py`)

For each fixture, its successful samples are pooled into five factor groups:

| Group | Symbol | Definition (per run) |
|---|---|---|
| size | S_f | tokens per appearance of family f |
| appearances | A_f | appearances of f per run (one appearance = one instance in one call) |
| price | P | effective price per token: input, cache read, cache write (TTL mix), output |
| cache | R_f, W_f | cache-read and cache-write share of f's tokens |
| output | O | output tokens per run |

```text
cost = Σ_f S_f · A_f · [(1 − R_f − W_f)·P_in + R_f·P_cr + W_f·P_cw] + O · P_out
```

Pooling is weighted so totals are preserved. `S·A` is the mean tokens per run, `S·A·R` is the mean cache-read
tokens per run, and each effective price is the run's token-weighted average across calls (this also covers mixed
models and long-context tiers). As a result, **modeled cost equals mean billed cost** whenever every call reported
usage. The *residual* in the comment is billed minus modeled. It is non-zero only when some tokens are estimates,
and a large one means the cost model is missing something, not that the attribution is wrong.

A family present on only one side enters the other side with `S = A = 0`, so its full cost is attributed rather
than dropped.

## 5. Attribution

For each fixture, all 2⁵ = 32 mixes are evaluated, taking head values for a subset of groups and base values for
the rest. This is arithmetic on recorded data, with no API calls. Each group's contribution is its Shapley value:
its marginal effect averaged over every order of switching the groups from base to head.

- **Exact.** Contributions sum to `modeled(head) − modeled(base)`.
- **Order-free.** No group order is assumed. Interaction effects, such as a bigger segment carried through more
  steps, are split evenly between the groups involved.
- **Per family.** The model is a sum of independent per-family terms plus an output term. Shapley values are
  additive, so each term is decomposed on its own, and the per-family split within each group is exact, not an
  approximation.
- **Across fixtures.** Contributions are averaged over fixtures. Linearity keeps the sum exact.

`explain.py` groups contributions into findings: per family (size + appearances), cache (summed over families),
price, and output. It ranks them by absolute dollar effect and writes one sentence for each. The comment shows the
top three that move at least 5% of the delta and 0.5% of the base cost per run.

## 6. Statistics and the gating rule (`stats.py`, `diff.py`)

| Metric | Definition |
|---|---|
| cost per run (p50) | mean over fixtures of each fixture's median cost per run |
| p90 cost | 90th percentile of cost per run over all runs |
| pass rate | mean over graded fixtures of each fixture's pass fraction |

**Bootstrap.** 2,000 iterations, two levels: resample fixtures with replacement (base and head stay paired), then
resample samples within each fixture on each side. The second level keeps run-to-run noise in the interval, so a
suite with few fixtures can't produce a falsely tight interval. The seed is fixed, so the same reports give the
same output.

**Verdicts.** For the relative change in p50 and p90 cost:

- whole 95% interval above `max_regression` → **regression** (exit 1)
- interval straddles the threshold → **inconclusive** (exit 0; more samples would settle it)
- otherwise → **within budget** (exit 0)

Absolute budgets (`cost_per_run_p50`, `cost_per_run_p90`) apply the same rule to the head's bootstrap interval.
Quality applies it to the drop in pass rate against `max_quality_drop`. Any regression verdict fails the check.

## 7. Baselines and drift (`ci.py`)

The comparison is always **merge base vs. PR head**, so the delta holds only the PR's own changes. Every push to
`main` uploads its report as the artifact `agentcost-baseline-<sha>`. On a PR:

1. The job checks out the PR head itself, not GitHub's test merge with current main.
2. It looks up the artifact for `git merge-base origin/main HEAD`.
3. If the artifact exists and is no older than `ci.baseline_max_age_days` (7 by default), only the head is run.
   Otherwise base and head run interleaved in the same job, with the base checked out in a temporary git worktree.
4. **Drift check.** With a cached baseline, any `tool_result` family's tokens per run or the step count that
   differs significantly (bootstrap interval entirely beyond ±10%) triggers a same-time re-run of base and head,
   and the report uses that fresh pair. Live tools can drift between days. This keeps every tool-related
   regression that gets reported coming from a same-time pair, and spend doubles only on PRs that look suspicious.
5. Costs are computed at diff time from token counts using the current price table, so a provider price change
   never shows up as a PR regression.

`baseline: fresh` skips the cache and always runs both sides together.

## 8. Known limits

- **Divergent paths.** Instances are matched by family and ordinal. When base and head take different paths
  (different tools, different orders), cost moves between families, and the attribution reports it that way.
- **Frameworks that rewrite history** produce `mutated` segments. Attribution stays exact at the group level, but
  the cause inside `mutated` is not named.
- **The Claude Agent SDK** works if its CLI honors `ANTHROPIC_BASE_URL`. It compacts its own context and makes
  auxiliary calls, so expect many `mutated` segments.
- **No call-site attribution.** The proxy can't see which line of code made a call. File-and-line attribution
  needs an SDK-patching mode, which is not in v0.

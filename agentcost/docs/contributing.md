# Contributing

## Setup

```bash
cd agentcost
uv venv -p 3.12 .venv            # or: python -m venv .venv
make dev                         # editable install with the dev extra
make lint test                   # ruff + pyright, then the fast tests (offline, no API keys)
```

| Target | |
|---|---|
| `make dev` | Editable install with the `dev` extra (uses `uv` when available). |
| `make lint` / `make format` | ruff check + format check + pyright / auto-fix. |
| `make test` | All tests except the seeded benchmark (~25 s). |
| `make test-benchmark` | The seeded-regression acceptance test (~30 s). |
| `make benchmark ARGS="--exact"` | The benchmark as a readable table. |
| `make build` | Clean, run `make test`, then build the wheel and sdist into `dist/`. |
| `make install` | Build and install the wheel into `.venv`, replacing the editable install (run `make dev` to go back). |
| `make publish-test` / `make publish` | Build and upload to TestPyPI / PyPI with twine. |
| `make clean` | Remove build output. |

The dev extra installs the `anthropic` and `openai` SDKs. Tests drive the proxy with the real SDKs against local
fake servers.

## Layout

```text
src/ezop_agentcost/
  cli.py          click commands: init, run, diff, compare, ci
  config.py       agentcost.yml parsing, fixtures
  runner.py       subprocess runs, assertions, report.json
  proxy.py        recording proxy (Starlette + httpx), spend cap
  sse.py          SSE splitting and stream assemblers per API surface
  usage.py        provider-neutral billed usage
  pricing.py      versioned price table
  tokens.py       local and exact token counting
  segments.py     segment keys, carried-context matching, token allocation, cache-zone calibration
  attribution.py  factor pooling, cost model, Shapley decomposition
  stats.py        bootstrap and the gating rule
  diff.py         comparison, budgets, quality, drift check
  explain.py      findings and sentences
  render.py       PR comment and terminal summary
  ci.py           baseline lookup, paired runs, sticky comment, GitHub outputs
  gitutil.py      git helpers (merge base, worktrees)
  github.py       GitHub REST: artifacts, comments
  templates/      files written by `ezop-agentcost init`
examples/support_agent/
  support_agent/  the reference agent (five tools + a refinement loop)
  mock_claude.py  offline Messages API stand-in used by tests and the benchmark
  benchmark.py    the seeded-regression benchmark
action.yml        the composite GitHub Action
```

## Tests

| File | Covers |
|---|---|
| `test_pricing.py` | model id resolution, cache/TTL/long-context pricing, usage normalization |
| `test_sse.py` | event splitting under arbitrary chunking, the three stream assemblers |
| `test_proxy.py` | both SDKs through the proxy, streaming and not, usage-chunk hiding, spend cap, error relay |
| `test_segments.py` | keys, carried-turn matching, `mutated`, Responses chains, allocation, zone calibration |
| `test_attribution.py` | the spec's method checks: exact sums, order invariance, determinism |
| `test_stats.py` | gating rule, regression vs. no-op, intervals on tiny suites, reproducibility |
| `test_diff_render.py` | verdicts, budgets, quality, failures, rendering, drift check |
| `test_runner.py` | statuses (ok/crash/timeout/silent), assertions, exact token counts, config validation |
| `test_ci.py` | PR flow against a throwaway git repo: fresh pair, cached baseline, stale baseline, labels; GitHub client |
| `test_cli.py` | `init`, `diff` exit codes, config errors |
| `test_benchmark.py` | the seeded-regression benchmark (the MVP acceptance test) |

Skip the slowest part with `pytest -m "not benchmark"`.

## The seeded benchmark

The MVP's claim is that agentcost names the right cause. `examples/support_agent/benchmark.py` checks that claim.
Each scenario runs the reference agent with and without one seeded change, interleaved, and checks the share of the
delta given to the expected factor:

| # | Seeded change (`SUPPORT_AGENT_VARIANT`) | Expected |
|---|---|---|
| 1 | `full_line_items`: a tool returns full line items, ~4× larger | size of `tool_result:lookup_order` ≥ 80% |
| 2 | `longer_prompt`: system prompt +600 tokens | size of `system_prompt` ≥ 90% |
| 3 | `timestamp_top`: timestamp moved to the top of the prompt | cache ≥ 80% |
| 4 | `extra_refine`: one extra refinement iteration | appearances ≥ 50% |
| 5 | `pricier_model`: model swapped to a pricier tier | price ≥ 90% |
| 6 | `noop`: no behavior change | no gate |

```bash
cd examples/support_agent
python benchmark.py                 # offline against mock_claude.py: free, ~30 s
python benchmark.py --exact         # exact token counts (the mock serves count_tokens too)
python benchmark.py --live -n 3     # real API: needs ANTHROPIC_API_KEY, costs real money
```

Offline, the attribution scenarios run with deterministic mock output, so small true effects are measurable. Only
the no-op scenario adds output-length noise, to test that variance never gates. Each scenario starts with a cold
mock cache and one discarded warm-up run per side, so it measures steady state rather than first-call cache
writes.

`mock_claude.py` bills with its own tokenizer, deliberately different from ezop_agentcost's local counts, so the
scaling and calibration code is exercised for real. Shares above 100% (scenario 1 reads about 110% with
approximate counts and about 103% with exact counts) are that tokenizer mismatch showing through. They are
expected, and documented in [how-it-works.md](how-it-works.md#token-counting-tokenspy).

## Adding a provider surface

1. `proxy.classify`: map the path to an `api` name.
2. `usage.Usage.from_*`: normalize its billed usage.
3. `sse.py`: an assembler if it streams, registered in `make_assembler`.
4. `segments.py`: request and response block extraction, wired into `RunSegmenter.request_blocks` /
   `response_blocks`. Decide whether its cache boundaries fall on block boundaries; if they do, enable
   `calibrate`.
5. `pricing.py`: model prices.
6. Tests: a fake upstream in `tests/`, plus an end-to-end proxy test that uses the vendor's SDK.

## Updating prices

Edit `BUILTIN_PRICES` in `pricing.py` and bump `PRICE_TABLE_VERSION`. The version appears in every comment, so
reviewers can tell which table priced a report.

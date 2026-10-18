# Reference agent: Northbound support

A customer-support agent for a fictional outdoor-gear store. It is small enough to read in a few minutes and
realistic enough to make agentcost's job non-trivial:

- **five tools** (`lookup_order`, `lookup_customer`, `search_kb`, `check_refund_policy`, `create_ticket`) backed by
  seeded JSON in `data/`, so tool output is identical across runs
- **a tool loop**, followed by a **refinement pass** that re-reads the whole conversation
- **prompt caching**: a static policy prompt with a cache breakpoint, and the timestamp after it
- **streaming** via `client.messages.stream(...).get_final_message()`, on `claude-opus-5-5`

```bash
pip install -e "../..[dev]"              # agentcost plus the anthropic SDK

# Offline (free): run against the mock model
python mock_claude.py --port 8900 &
AGENTCOST_ANTHROPIC_UPSTREAM=http://127.0.0.1:8900 ANTHROPIC_API_KEY=mock ezop-agentcost run -n 1

# Live: real API calls
ANTHROPIC_API_KEY=sk-ant-... ezop-agentcost run -n 1
```

## Seeded regressions

`SUPPORT_AGENT_VARIANT` switches on a seeded change, so each one can be exercised without a branch per change:

| Variant | What changes | Where |
|---|---|---|
| `full_line_items` | `lookup_order` returns every line item with all its fields (~4× larger) | `tools.py` |
| `longer_prompt` | the system prompt gains a ~600-token brand voice guide | `prompts.py` |
| `timestamp_top` | the current time moves to the top of the cached system prompt | `agent.py` |
| `extra_refine` | one extra refinement iteration | `agent.py` |
| `pricier_model` | `claude-opus-5-5` → `claude-fable-5-1` | `agent.py` |
| `noop` | nothing (stands in for a refactor) | — |

```bash
python benchmark.py            # all six, offline, ~30 s
```

To see a PR comment for one change:

```bash
python mock_claude.py --port 8900 &
export AGENTCOST_ANTHROPIC_UPSTREAM=http://127.0.0.1:8900 ANTHROPIC_API_KEY=mock
ezop-agentcost run -o base.json
SUPPORT_AGENT_VARIANT=full_line_items ezop-agentcost run -o head.json
ezop-agentcost diff base.json head.json --comment comment.md
```

Comparing two separate `run`s works, but `benchmark.py` and `ezop-agentcost compare` interleave base and head, which is
the recommended way when tools return live data.

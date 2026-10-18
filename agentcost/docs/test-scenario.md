# Test scenario: agentcost on a realistic agent repo

A hands-on runbook for trying agentcost end to end before you rely on it. You'll play the developer of a customer
support agent who opens three pull requests:

| PR | Change | What agentcost should say |
|---|---|---|
| **PR 1** | `lookup_order` returns the full order "so the agent can do item-level refunds" | **Regression**, blamed on `tool_result:lookup_order` growing and being carried through every later call |
| **PR 1, fix-up commit** | trim line items to the five fields refunds need | **Within budget** (about +12%, under the 15% threshold); the sticky comment updates in place |
| **PR 2** | "make the agent date-aware" by putting the current time at the top of the system prompt | **Regression**, blamed on the **cache**: the cached prefix breaks at `system_prompt` |
| **PR 3** | docs-only change | **No change, no gate** |

The scenario runs in three stages, each building on the last:

1. **Offline** against the bundled mock model: free, about 5 minutes, no API key.
2. **Live** against the real Anthropic API from your laptop: about $1–5.
3. **GitHub**: the real PR workflow on a sandbox repository, with baselines, sticky comments, and the check status.

Numbers below were measured on the offline mock. Live numbers will differ, but the *direction* and the *named
cause* should not.

---

## Stage 0: Set up a sandbox agent repo

The reference agent in `examples/support_agent` becomes the sandbox: a five-tool support agent with a refinement
pass, prompt caching, and streaming on `claude-opus-5-5`.

```bash
# From the ezop repo root
mkdir -p ~/agentcost-sandbox
rsync -a --exclude __pycache__ --exclude benchmark.py --exclude README.md \
  agentcost/examples/support_agent/ ~/agentcost-sandbox/
cd ~/agentcost-sandbox
printf '.venv/\n.agentcost/\n__pycache__/\n' > .gitignore

python3 -m venv .venv && source .venv/bin/activate
pip install anthropic ~/path/to/ezop/agentcost      # or, once published: pip install ezop-agentcost

git init -b main && git add . && git commit -m "Support agent v1"
```

You now have `agentcost.yml` (6 fixtures × 3 samples, 15% threshold, $0.18/run p50 budget, $15 spend cap),
fixtures with assertions, and the agent under `support_agent/`.

**Check:** `ezop-agentcost --version` prints `0.1.0`.

---

## Stage 1: Offline, against the mock model

Start the mock and point agentcost's proxy at it. The mock scripts the agent's tool calls, bills usage with its own
tokenizer, and simulates prompt caching.

```bash
python mock_claude.py --port 8900 &
export AGENTCOST_ANTHROPIC_UPSTREAM=http://127.0.0.1:8900 ANTHROPIC_API_KEY=mock
ezop-agentcost run -n 1          # smoke test: 6 runs, all "ok pass", ~7 calls each
```

**Check:** `6/6 runs ok`, and no warning about zero recorded calls.

### PR 1: return the full order

```bash
git checkout -b feature/item-level-refunds
```

In `support_agent/tools.py`, replace the summarization at the end of `lookup_order`:

```diff
-    summary = {k: v for k, v in order.items() if k != "line_items"}
-    summary["items"] = [{"name": li["name"], "qty": li["qty"]} for li in order["line_items"]]
-    return summary
+    return order  # item-level refunds need every line item
```

```bash
git commit -am "Return full line items from lookup_order"
ezop-agentcost compare --base main; echo "exit=$?"
```

Expected (measured):

```text
Cost per run     $0.017 → $0.026    +49%  (95% CI +45% to +57%)  REGRESSION
p90 cost         $0.021 → $0.033    +52%  (95% CI +44% to +72%)  REGRESSION
Pass rate          100% → 100%            no significant drop
Steps per run       6.2 → 6.2

Of the +$0.0088 mean increase per run:
1. +$0.0094  tool_result:lookup_order grew 204 → 657 tokens and is carried
            through 5.2 calls
exit=1
```

**What to verify**

- [ ] Verdict is `REGRESSION` and the exit code is `1`.
- [ ] Finding #1 names `tool_result:lookup_order`, not the system prompt or "input tokens".
- [ ] "Carried through ~5 calls" matches reality: the order is looked up first, and every later call re-sends it.
- [ ] Pass rate is unchanged: the change is more expensive, not better.
- [ ] `.agentcost/comment.md` holds the PR comment; open it in a Markdown preview.

### PR 1, fix-up commit: trim the line items

```diff
-    return order  # item-level refunds need every line item
+    keep = ("sku", "name", "qty", "unit_price", "returnable")
+    summary = {k: v for k, v in order.items() if k != "line_items"}
+    summary["items"] = [{k: li[k] for k in keep} for li in order["line_items"]]
+    return summary
```

```bash
git commit -am "Trim line items to the fields refunds need"
ezop-agentcost compare --base main; echo "exit=$?"
```

Expected (measured):

```text
Cost per run     $0.018 → $0.020    +12%  (95% CI +10% to +15%)  within budget
p90 cost         $0.021 → $0.025    +16%  (95% CI +10% to +18%)  INCONCLUSIVE
1. +$0.0031  tool_result:lookup_order grew 204 → 352 tokens ...
exit=0
```

**What to verify**

- [ ] Exit code `0`. The PR still costs a bit more, but the whole interval sits under the 15% threshold.
- [ ] p90 is `INCONCLUSIVE`, which is reported but does not gate. This is the rule that keeps teams from muting the
  check.
- [ ] The finding still names the same segment, now with a smaller delta.

### PR 2: put the date first

```bash
git checkout main && git checkout -b feature/date-aware
```

In `support_agent/agent.py`, `system_blocks()`:

```diff
     return [
-        {"type": "text", "text": policy, "cache_control": {"type": "ephemeral"}},
-        {"type": "text", "text": f"Current time: {now}"},
+        {"type": "text", "text": f"Current time: {now}\n\n{policy}", "cache_control": {"type": "ephemeral"}},
     ]
```

```bash
git commit -am "Put the current date first so the agent reasons about deadlines"
ezop-agentcost compare --base main; echo "exit=$?"
```

Expected (measured):

```text
Cost per run     $0.018 → $0.063   +257%  (95% CI +246% to +272%)  REGRESSION
1.  +$0.045  cache hit rate 80% → 0%, cache writes 0% → 81% of input (cached
            prefix broken at system_prompt: content that changes early in
            the prompt invalidates the cache)
exit=1
```

**What to verify**

- [ ] The cause is the **cache**, not the prompt size. The prompt got only a few tokens longer, so a totals-based
  tool would show "+257%" with no explanation.
- [ ] The hit rate falls to 0% and cache writes jump, because every call now writes a fresh prefix.

### PR 3: a no-op

```bash
git checkout main && git checkout -b docs/readme
echo "# Northbound support agent" > README.md && git add README.md && git commit -m "Add README"
ezop-agentcost compare --base main; echo "exit=$?"
```

**What to verify**

- [ ] Within budget, interval around 0%, exit `0`, and no findings ("no cost change to explain").

Stop the mock when you're done: `kill %1`.

---

## Stage 2: Live, against the real Anthropic API

Same PRs, now with real model behavior: real tokenization, real output-length variance, real caching.

```bash
unset AGENTCOST_ANTHROPIC_UPSTREAM
export ANTHROPIC_API_KEY=sk-ant-...
```

**Keep the first live run small.** In `agentcost.yml` on the branch you are testing, set:

```yaml
samples: 2
spend_cap_usd: 5
```

Then run a subset of fixtures:

```bash
git checkout feature/item-level-refunds
ezop-agentcost run -n 1 -f damaged_backpack        # one real run first: check it works and what it costs
ezop-agentcost compare --base main -f damaged_backpack,wrong_item,warranty
```

`compare` reads the config from the branch you're on and uses it for both sides, so the cheaper settings apply to
the base run too.

**Cost.** `run` prints the spend, and `.agentcost/head.json` records `spend_usd`. Expect very roughly $0.05–0.20
per run on `claude-opus-5-5`. A paired compare over 3 fixtures × 2 samples is 12 runs. The spend cap stops the
check if your estimate is off.

**What to verify**

- [ ] Every run is `ok`, with ~6–7 calls each. A run with zero calls means the agent bypassed the proxy.
- [ ] PR 1 is still a regression, blamed on `tool_result:lookup_order`.
- [ ] PR 2 is still blamed on the cache. If the hit rate is *already* low on main, your prompt is below the model's
  minimum cacheable size, which is a finding in its own right.
- [ ] `Model vs. billed residual` is about $0.0000.
- [ ] Re-run PR 1 with `token_counts: exact` in the config. The finding stays the same, and the share given to
  `lookup_order` gets tighter.
- [ ] Re-run PR 3 (no-op) twice. Real output-length noise should make it *within budget*, never *REGRESSION*. A
  no-op that gates is a bug worth reporting.

---

## Stage 3: The GitHub workflow

This stage exercises what CI adds on top of `compare`: baselines stored from `main`, merge-base pairing, the
sticky comment, and the check status.

### Set up

1. Create a **private** sandbox repository on GitHub and push the sandbox `main` to it.
2. Add `ANTHROPIC_API_KEY` under Settings → Secrets and variables → Actions.
3. Add the workflow. `ezop-agentcost init --dir .` writes one, or copy it from below. The action is referenced
   from wherever the ezop repo is pushed. Use your fork or branch until a release exists.

```yaml
# .github/workflows/agentcost.yml
name: agentcost
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
  actions: read
  pull-requests: write
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
      - run: pip install anthropic
      - uses: <owner>/ezop/agentcost/ci/github@<branch-or-tag>
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

To test a published package instead of the action's source, add
`install: ezop-agentcost==0.1.0` under `with:`. For TestPyPI, use
`install: "-i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple ezop-agentcost==0.1.0"`.

Use the small live settings (`samples: 2`, a fixture subset, `spend_cap_usd: 5`) while trying it out. Every PR push
costs real money.

### Walk through it

| Step | Do | Expect |
|---|---|---|
| 1 | Push the workflow to `main` | The run's mode is **baseline**. Artifacts include `agentcost-baseline-<sha>`. |
| 2 | Push `feature/item-level-refunds` (the first commit only) and open a PR | One comment: **Significant cost or quality regression**, naming `lookup_order`. The check fails. The log says *"cached baseline from main … running head only"*. |
| 3 | Push the fix-up commit to the same PR | The **same** comment is edited in place to **Within budget**, and the check passes. No second comment. |
| 4 | Open PR 2 (date first) | Regression comment blaming the cache. |
| 5 | Open PR 3 (docs only) | Within budget, no findings. |
| 6 | Delete the baseline artifact (Actions → run → Artifacts) and re-run PR 3 | The log says *"no cached baseline … running base and head interleaved"*. Same verdict; double the spend. |
| 7 | Set `ci: {run_on_label: agentcost}` on a branch and open a PR | Check passes with verdict `skipped` and no comment. Add the `agentcost` label and re-run: it runs. |
| 8 | In `data/orders.json`, add a field to every order, commit on a branch **without** touching code, and open a PR | The **drift check** fires (*"tool_result:lookup_order tokens per run changed …"*), and base and head re-run together. The report blames the tool result, from a same-time pair. |

**What to verify along the way**

- [ ] The base commit in the comment's details is the **merge base**, not current `main`. Push a commit to `main`
  after opening PR 2 and re-run: the base must not change.
- [ ] The job summary shows the same comment, and the `agentcost-pr-*` artifact holds `base.json`, `head.json`,
  `diff.json`, and `comment.md`.
- [ ] Making the check required (Settings → Branches) blocks merging PR 1's first commit, but not after the fix-up.

---

## Pass criteria

agentcost passes this scenario when:

1. Every regression PR names the cause you actually introduced: tool result size for PR 1, cache for PR 2.
2. No-op and docs-only PRs never gate, live, across repeated runs.
3. The comment is sticky (one per PR) and updates on each push.
4. Live spend stays under the cap, and the per-check cost is acceptable to you.
5. Setup on the sandbox repo, from `init` to the first PR comment, took under 30 minutes. This is the MVP's
   adoption bar.

If any step disagrees with this runbook, keep `.agentcost/diff.json` and the run's `--keep-payloads` output. Those
two files are enough to reproduce the problem.

## Clean up

```bash
rm -rf ~/agentcost-sandbox
```

Delete the sandbox GitHub repository, or at least its `ANTHROPIC_API_KEY` secret.

# Report format

agentcost writes two JSON documents. Both are meant for tooling: build a dashboard from them, or feed them to
another check. Neither contains prompt or response content.

## `report.json` (one side of a comparison)

Written by `ezop-agentcost run` and by CI, as `base.json`, `head.json`, or `baseline/report.json`.

```jsonc
{
  "schema_version": 1,
  "agentcost_version": "0.1.0",
  "name": "support-agent",
  "variant": "head",                    // head | base | baseline
  "commit": "def456…",                  // null outside a git repo
  "created_at": "2026-10-17T12:00:00+00:00",
  "samples": 3,
  "fixtures": ["damaged_backpack", "..."],
  "token_counting": "approx (412 segments), openai (20 segments)",
  "spend_usd": 6.91,                    // whole check, both sides when paired
  "capped": false,
  "agent": {"run": "python -m support_agent.run --input {fixture} --output {output}"},
  "warnings": ["2 run(s) recorded zero LLM calls. ..."],
  "runs": [
    {
      "run_id": "head-damaged_backpack-s1-4f1607",
      "fixture": "damaged_backpack",
      "sample": 1,
      "status": "ok",                   // ok | crashed | timeout | capped
      "exit_code": 0,
      "duration_s": 4.21,
      "passed": true,                   // null when the fixture has no assertion or the run failed
      "assert_error": null,
      "error": null,
      "stderr_tail": "...",             // failed runs only: last 2,000 characters
      "calls": [
        {
          "seq": 1,                     // call order within the run
          "api": "anthropic.messages",  // | openai.chat | openai.responses
          "model": "claude-opus-5-5",
          "status": 200,
          "streamed": true,
          "latency_ms": 1830.4,
          "usage": {"input": 312, "cache_read": 2051, "cache_write_5m": 0, "cache_write_1h": 0, "output": 41},
          "estimated": false,           // true: no usage reported; tokens are local estimates
          "segments": [
            {"key": "overhead", "tokens": 322.1, "cache_read": 322.1, "cache_write": 0},
            {"key": "tool_schemas", "tokens": 610.4, "cache_read": 610.4, "cache_write": 0},
            {"key": "system_prompt", "tokens": 1131.0, "cache_read": 1118.5, "cache_write": 0},
            {"key": "user_input", "tokens": 25.0, "cache_read": 0, "cache_write": 0}
          ]
        }
      ]
    }
  ]
}
```

Rules worth knowing:

- `usage.input` is the **uncached** part of the prompt. The full prompt is `input + cache_read + cache_write_5m +
  cache_write_1h`.
- Each call's `segments[].tokens` sum to its full prompt (to float precision). `cache_read` and `cache_write` sum
  to the billed values.
- Costs are deliberately absent. They are computed at diff time with the current price table.
- Calls with an HTTP error have `usage: null`, `segments: []`, and an `error` string.

## `diff.json` (the comparison)

Written by `ezop-agentcost diff --json` and by CI.

```jsonc
{
  "verdict": "regression",              // regression | inconclusive | ok | error
  "exit_code": 1,
  "error": null,                        // set when verdict is "error"
  "fixtures": ["..."],                  // fixtures with successful runs on both sides
  "unmatched_fixtures": {"base_only": [], "head_only": ["new_case"]},
  "failures": {"base": {}, "head": {"timeout": 1}},
  "cost": {
    "base_p50": 0.142, "head_p50": 0.191, "base_p90": 0.31, "head_p90": 0.52,
    "base_mean": 0.145, "head_mean": 0.194,
    "p50_change": {"point": 0.34, "low": 0.22, "high": 0.47},
    "p90_change": {"point": 0.68, "low": 0.41, "high": 0.90},
    "p50_verdict": "regression", "p90_verdict": "regression"
  },
  "budgets": {"cost_per_run_p50": {"limit": 0.18, "head": {"point": 0.191, "low": 0.183, "high": 0.2}, "verdict": "regression"}},
  "quality": {"graded_fixtures": 15, "base_pass_rate": 0.91, "head_pass_rate": 0.92,
              "drop": {"point": -0.01, "low": -0.06, "high": 0.04}, "max_quality_drop": 0.05, "verdict": "ok"},
  "steps": {"base": 6.1, "head": 6.3},
  "attribution": {
    "modeled_delta": 0.049, "billed_delta": 0.049, "residual": 0.0,
    "groups": {"size": 0.047, "appearances": 0.0, "price": 0.0, "cache": 0.002, "output": 0.0},
    "contributions": [{"group": "size", "family": "tool_result:lookup_order", "value": 0.038}],
    "findings": [{"kind": "family", "subject": "tool_result:lookup_order", "value": 0.038,
                  "sentence": "`tool_result:lookup_order` grew 2.1K → 9.4K tokens and is carried through 6 calls",
                  "groups": {"size": 0.036, "appearances": 0.002}}],
    "per_fixture": {"damaged_backpack": {"base_mean_cost": 0.13, "head_mean_cost": 0.17, "modeled_delta": 0.04}},
    "cache_hit_rate": {"base": 0.71, "head": 0.58},
    "output_tokens": {"base": 410, "head": 415}
  },
  "token_counting": {"base": "...", "head": "..."},
  "price_table": "2026-10-17",
  "baseline_note": "Baseline: cached baseline from main (1.2 days old); drift check passed.",
  "warnings": []
}
```

All money is USD per run. `contributions` lists every (group, family) pair, sorted by absolute value. The output
term uses the family name `(output)`. `sum(contributions[].value) == modeled_delta` holds to floating-point
precision.

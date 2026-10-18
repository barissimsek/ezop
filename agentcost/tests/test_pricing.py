import pytest

from ezop_agentcost.pricing import PriceTable, UnknownModelError
from ezop_agentcost.usage import Usage


def test_lookup_exact_dated_and_cloud_prefixed_ids():
    t = PriceTable()
    assert t.get("claude-opus-5-5").input == 4.0
    assert t.get("claude-haiku-4-5-20251001").input == 1.0
    assert t.get("us.anthropic.claude-sonnet-4-5-20250929-v1:0").input == 3.0
    assert t.get("claude-opus-4-5@20251101").input == 5.0
    assert t.get("gpt-4o-mini-2024-07-18").input == 0.15  # longest prefix wins over gpt-4o
    assert t.get("gpt-5.4-mini").input == 0.75
    assert t.lookup("gpt-4.1x") is None  # no match across a non-boundary character


def test_unknown_model_message_points_at_overrides():
    with pytest.raises(UnknownModelError, match="pricing.overrides"):
        PriceTable().get("my-finetune")


def test_cost_includes_cache_read_write_ttl_and_output():
    p = PriceTable().get("claude-sonnet-4-6")  # $3 in, $15 out, read 0.1x, write 1.25x / 2x
    u = Usage(
        input=1_000_000, cache_read=1_000_000, cache_write_5m=1_000_000, cache_write_1h=1_000_000, output=1_000_000
    )
    assert p.cost(u) == pytest.approx(3 + 0.3 + 3.75 + 6 + 15)


def test_long_context_tier():
    p = PriceTable().get("claude-haiku-5-5")
    short = Usage(input=100_000, output=1000)
    long = Usage(input=100_001, output=1000)
    assert p.cost(short) == pytest.approx((100_000 * 0.10 + 1000 * 0.50) / 1e6)
    assert p.cost(long) == pytest.approx((100_001 * 0.50 + 1000 * 2.50) / 1e6)


def test_from_config_overrides_and_table_none():
    t = PriceTable.from_config({"overrides": {"my-model": {"input": 1, "output": 2}}})
    assert t.get("my-model").cache_read == pytest.approx(0.1)
    assert t.get("claude-opus-5-5").input == 4.0
    only = PriceTable.from_config({"table": "none", "overrides": {"m": {"input": 1, "output": 2, "cache_read": 0.5}}})
    assert only.lookup("claude-opus-5-5") is None
    assert only.get("m").cache_read == 0.5
    with pytest.raises(ValueError):
        PriceTable.from_config({"overrides": {"m": {"input": 1}}})


def test_usage_normalization():
    a = Usage.from_anthropic(
        {
            "input_tokens": 10,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 30,
            "cache_creation": {"ephemeral_5m_input_tokens": 20, "ephemeral_1h_input_tokens": 10},
            "output_tokens": 5,
        }
    )
    assert (a.input, a.cache_read, a.cache_write_5m, a.cache_write_1h, a.total_input) == (10, 100, 20, 10, 140)
    o = Usage.from_openai_chat(
        {"prompt_tokens": 100, "completion_tokens": 9, "prompt_tokens_details": {"cached_tokens": 64}}
    )
    assert (o.input, o.cache_read, o.output) == (36, 64, 9)
    r = Usage.from_openai_responses(
        {"input_tokens": 50, "input_tokens_details": {"cached_tokens": 10}, "output_tokens": 3}
    )
    assert (r.input, r.cache_read, r.output) == (40, 10, 3)

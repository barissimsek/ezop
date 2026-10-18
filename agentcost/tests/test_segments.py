import pytest

from ezop_agentcost.segments import allocate, segment_run, zone_scales
from ezop_agentcost.tokens import TokenCounter
from ezop_agentcost.usage import Usage

TOOLS = [{"name": "lookup_order", "description": "d", "input_schema": {"type": "object"}}]
SYSTEM = [{"type": "text", "text": "You are a support agent. " * 40, "cache_control": {"type": "ephemeral"}}]


def counter():
    return TokenCounter(prefer="heuristic")


def anth_call(seq, messages, response_content, usage):
    return {
        "seq": seq,
        "api": "anthropic.messages",
        "model": "claude-opus-5-5",
        "status": 200,
        "request": {"model": "claude-opus-5-5", "tools": TOOLS, "system": SYSTEM, "messages": messages},
        "response": {"content": response_content, "model": "claude-opus-5-5"},
        "usage": usage,
    }


def keys(call):
    return [s["key"] for s in call["segments"]]


def test_anthropic_run_keys_carried_turns_and_mutation():
    tool_use = {"type": "tool_use", "id": "toolu_1", "name": "lookup_order", "input": {"order_id": "1042"}}
    first_out = [{"type": "text", "text": "Let me check."}, tool_use]
    user = {"role": "user", "content": "Where is order 1042?"}
    assistant = {"role": "assistant", "content": [{**first_out[0], "citations": None}, tool_use]}
    result = {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"status":"shipped"}'}],
    }
    u = {"input": 500, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0, "output": 10}
    calls = [
        anth_call(1, [user], first_out, u),
        anth_call(2, [user, assistant, result], [{"type": "text", "text": "Shipped."}], u),
        anth_call(3, [user, assistant, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1",
                  "content": "[summarized]"}]}], [{"type": "text", "text": "x"}], u),
    ]  # fmt: skip
    out = segment_run(calls, counter())
    assert keys(out[0]) == ["overhead", "tool_schemas", "system_prompt", "user_input"]
    assert set(keys(out[1])) == {"overhead", "tool_schemas", "system_prompt", "user_input", "assistant_turn#1",
                                 "tool_result:lookup_order#1"}  # fmt: skip
    assert "mutated" in keys(out[2]) and "tool_result:lookup_order#1" not in keys(out[2])
    for c in out:
        assert sum(s["tokens"] for s in c["segments"]) == pytest.approx(500, abs=0.01)


def test_system_prompt_with_changing_timestamp_keeps_one_key():
    u = {"input": 500, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0, "output": 1}
    calls = []
    for i in range(3):
        system = [*SYSTEM, {"type": "text", "text": f"Current time: 2026-10-18T07:11:5{i}"}]
        rec = anth_call(i + 1, [{"role": "user", "content": "hi"}], [{"type": "text", "text": f"a{i}"}], u)
        rec["request"]["system"] = system
        calls.append(rec)
    out = segment_run(calls, counter())
    assert all("system_prompt" in keys(c) and not any(k.startswith("system_prompt#") for k in keys(c)) for c in out)


def test_unknown_assistant_content_is_mutated():
    u = {"input": 100, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0, "output": 1}
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "a summary the framework wrote"},
        {"role": "user", "content": "go on"},
    ]
    out = segment_run([anth_call(1, msgs, [], u)], counter())
    assert set(keys(out[0])) == {"overhead", "tool_schemas", "system_prompt", "user_input", "mutated", "user_message#1"}


def test_repeated_identical_user_messages_are_separate_instances():
    u = {"input": 200, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0, "output": 1}
    refine = "Review your draft."
    msgs = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": [{"type": "text", "text": "a1"}]},
        {"role": "user", "content": refine},
        {"role": "assistant", "content": [{"type": "text", "text": "a2"}]},
        {"role": "user", "content": refine},
    ]
    calls = [
        anth_call(1, msgs[:1], [{"type": "text", "text": "a1"}], u),
        anth_call(2, msgs[:3], [{"type": "text", "text": "a2"}], u),
        anth_call(3, msgs, [{"type": "text", "text": "a3"}], u),
    ]
    out = segment_run(calls, counter())
    assert {"user_message#1", "user_message#2", "assistant_turn#1", "assistant_turn#2"} <= set(keys(out[2]))


def test_allocate_cache_prefix_and_exact_totals():
    named = [
        ("overhead", 10),
        ("tool_schemas", 100),
        ("system_prompt", 400),
        ("user_input", 50),
        ("tool_result:x#1", 300),
    ]
    usage = Usage(input=300, cache_read=600, cache_write_5m=0, output=5)
    segs, estimated = allocate(named, usage, calibrate=True)
    by = {s.key: s for s in segs}
    assert not estimated
    assert sum(s.tokens for s in segs) == pytest.approx(900)
    assert sum(s.cache_read for s in segs) == pytest.approx(600)
    # The read zone (overhead + tools + system) is scaled to exactly the billed cache read.
    assert by["system_prompt"].cache_read == pytest.approx(by["system_prompt"].tokens)
    assert by["tool_result:x#1"].cache_read == pytest.approx(0, abs=1e-9)


def test_zone_scales_keeps_prefix_stable_when_tail_changes():
    # Same prefix, tail grows; the local tokenizer undercounts the tail by 2x.
    small = zone_scales([100, 400, 100], target=1000 + 400, read=1000, write=0)
    large = zone_scales([100, 400, 400], target=1000 + 1600, read=1000, write=0)
    assert small[:2] == pytest.approx(large[:2])
    assert small[2] == pytest.approx(4.0) and large[2] == pytest.approx(4.0)


def test_zone_scales_falls_back_to_uniform_off_boundary():
    # The only boundary would need 0.5x before and 2.7x after: no segment boundary fits a read of 50.
    s = zone_scales([100, 100], target=400, read=50, write=0)
    assert s == [2.0, 2.0]


def test_missing_usage_is_estimated():
    segs, estimated = allocate([("user_input", 40)], None)
    assert estimated and sum(s.tokens for s in segs) == 40


def test_openai_chat_tool_names_from_tool_calls():
    req = {
        "model": "gpt-5",
        "tools": [{"type": "function", "function": {"name": "search"}}],
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "find x"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "search", "arguments": '{"q":"x"}'}}]},
            {"role": "tool", "tool_call_id": "call_1", "content": "result"},
        ],
    }  # fmt: skip
    rec = {"seq": 1, "api": "openai.chat", "model": "gpt-5", "status": 200, "request": req, "response": {},
           "usage": {"input": 80, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0, "output": 2}}  # fmt: skip
    out = segment_run([rec], counter())
    assert "tool_result:search#1" in keys(out[0])
    assert "mutated" in keys(out[0])  # assistant tool call not produced by a recorded call in this run


def test_responses_previous_response_id_chain():
    u = {"input": 100, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0, "output": 3}
    first = {
        "seq": 1, "api": "openai.responses", "model": "gpt-5", "status": 200,
        "request": {"model": "gpt-5", "instructions": "be brief", "input": "what is 2+2?"},
        "response": {"id": "resp_1", "output": [{"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "4"}]}]},
        "usage": u,
    }  # fmt: skip
    second = {
        "seq": 2, "api": "openai.responses", "model": "gpt-5", "status": 200,
        "request": {"model": "gpt-5", "instructions": "be brief", "previous_response_id": "resp_1", "input": "and 3+3?"},
        "response": {"id": "resp_2", "output": []},
        "usage": u,
    }  # fmt: skip
    orphan = {**second, "seq": 3, "request": {**second["request"], "previous_response_id": "resp_unknown"}}
    out = segment_run([first, second, orphan], counter())
    assert {"user_input", "assistant_turn#1", "user_message#1", "system_prompt"} <= set(keys(out[1]))
    assert out[2].get("unresolved_context") and "mutated" in keys(out[2])


def test_error_calls_have_no_segments():
    rec = {"seq": 1, "api": "anthropic.messages", "model": "m", "status": 529, "request": {}, "response": None,
           "usage": None, "error": {"type": "overloaded_error"}}  # fmt: skip
    out = segment_run([rec], counter())
    assert out[0]["segments"] == [] and "overloaded" in out[0]["error"]

import asyncio
import json

from ezop_agentcost.sse import (
    AnthropicStreamAssembler,
    OpenAIChatStreamAssembler,
    OpenAIResponsesStreamAssembler,
    iter_sse,
)


def events(raw: bytes, chunk: int = 7):
    async def gen():
        for i in range(0, len(raw), chunk):
            yield raw[i : i + chunk]

    async def collect():
        return [e async for e in iter_sse(gen())]

    return asyncio.run(collect())


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def test_split_keeps_raw_bytes_across_arbitrary_chunking():
    raw = sse("a", {"x": 1}) + b"data: [DONE]\r\n\r\n" + sse("b", {"y": 2})
    evs = events(raw, chunk=3)
    assert b"".join(e.raw for e in evs) == raw
    assert [e.event for e in evs] == ["a", None, "b"]
    assert evs[1].data == "[DONE]"


def test_anthropic_assembler_rebuilds_message_and_cumulative_usage():
    raw = b"".join(
        [
            sse("message_start", {"type": "message_start", "message": {"id": "m1", "model": "claude-opus-5-5",
                "role": "assistant", "content": [], "usage": {"input_tokens": 12, "cache_read_input_tokens": 900,
                "cache_creation_input_tokens": 0, "output_tokens": 1}}}),
            sse("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
            sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}}),
            sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "lo"}}),
            sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
            sse("content_block_start", {"type": "content_block_start", "index": 1,
                "content_block": {"type": "tool_use", "id": "t1", "name": "lookup", "input": {}}}),
            sse("content_block_delta", {"type": "content_block_delta", "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '{"id": "10'}}),
            sse("content_block_delta", {"type": "content_block_delta", "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '42"}'}}),
            sse("content_block_stop", {"type": "content_block_stop", "index": 1}),
            sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"},
                "usage": {"output_tokens": 40, "input_tokens": None}}),
            sse("message_stop", {"type": "message_stop"}),
        ]
    )  # fmt: skip
    a = AnthropicStreamAssembler()
    for e in events(raw):
        a.feed(e)
    msg = a.result()
    assert msg["content"][0] == {"type": "text", "text": "Hello"}
    assert msg["content"][1]["input"] == {"id": "1042"}
    assert msg["stop_reason"] == "tool_use"
    assert a.usage_payload() == {
        "input_tokens": 12,
        "cache_read_input_tokens": 900,
        "cache_creation_input_tokens": 0,
        "output_tokens": 40,
    }


def test_openai_chat_assembler_tool_calls_and_usage_chunk():
    chunks = [
        {"id": "c1", "model": "gpt-5", "choices": [{"index": 0, "delta": {"role": "assistant", "tool_calls": [
            {"index": 0, "id": "call_1", "function": {"name": "lookup", "arguments": '{"a"'}}]}}]},
        {"id": "c1", "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": ": 1}"}}]},
                                  "finish_reason": "tool_calls"}]},
        {"id": "c1", "choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 5}},
    ]  # fmt: skip
    raw = b"".join(f"data: {json.dumps(c)}\n\n".encode() for c in chunks) + b"data: [DONE]\n\n"
    a = OpenAIChatStreamAssembler()
    evs = events(raw)
    for e in evs:
        a.feed(e)
    msg = a.result()["choices"][0]["message"]
    assert msg["tool_calls"][0]["function"] == {"name": "lookup", "arguments": '{"a": 1}'}
    assert a.usage_payload()["prompt_tokens"] == 20
    assert [OpenAIChatStreamAssembler.is_usage_only(e) for e in evs] == [False, False, True, False]


def test_responses_assembler_takes_terminal_event():
    resp = {"id": "r1", "output": [], "usage": {"input_tokens": 5, "output_tokens": 1}}
    raw = sse("response.created", {"type": "response.created", "response": {"id": "r1"}}) + sse(
        "response.completed", {"type": "response.completed", "response": resp}
    )
    a = OpenAIResponsesStreamAssembler()
    for e in events(raw):
        a.feed(e)
    assert a.result() == resp
    assert a.usage_payload() == resp["usage"]

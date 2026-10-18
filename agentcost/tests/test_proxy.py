"""End to end through the recording proxy with the official SDKs."""

import anthropic
import httpx
import openai
import pytest

from ezop_agentcost.pricing import PriceTable
from ezop_agentcost.proxy import RecordingProxy, classify, resolve_upstreams


@pytest.fixture
def proxy(mock_claude, fake_openai, tmp_path):
    server, _ = mock_claude
    with RecordingProxy(
        PriceTable(),
        spend_cap_usd=None,
        payload_dir=tmp_path / "payloads",
        upstreams={"anthropic": server.url, "openai": fake_openai.url},
        port=0,
    ) as p:
        yield p


def anthropic_client(proxy, run_id):
    return anthropic.Anthropic(api_key="test", base_url=proxy.env_for(run_id)["ANTHROPIC_BASE_URL"], max_retries=0)


def openai_client(proxy, run_id):
    return openai.OpenAI(api_key="test", base_url=proxy.env_for(run_id)["OPENAI_BASE_URL"], max_retries=0)


MSG = [{"role": "user", "content": "Hi, my order 1042 arrived damaged."}]


def test_anthropic_non_streaming_and_streaming_are_recorded(proxy):
    client = anthropic_client(proxy, "r1")
    resp = client.messages.create(model="claude-opus-5-5", max_tokens=100, messages=MSG)
    assert resp.content[1].name == "lookup_order"
    with client.messages.stream(model="claude-opus-5-5", max_tokens=100, messages=MSG) as stream:
        final = stream.get_final_message()
    assert final.content[1].input == {"order_id": "1042"}

    calls = proxy.recorder.collect("r1")
    assert [c["seq"] for c in calls] == [1, 2]
    assert [c["streamed"] for c in calls] == [False, True]
    for c in calls:
        assert c["api"] == "anthropic.messages" and c["status"] == 200
        assert c["usage"]["output"] > 0 and c["usage"]["input"] > 0
        assert c["request"]["messages"] == MSG
    assert calls[1]["response"]["content"][1]["input"] == {"order_id": "1042"}
    assert (proxy.recorder.payload_dir / "r1.jsonl").read_text().count("\n") == 2


def test_api_key_is_forwarded_but_never_recorded(proxy, tmp_path):
    client = anthropic.Anthropic(api_key="sk-secret-123", base_url=proxy.env_for("r2")["ANTHROPIC_BASE_URL"])
    client.messages.create(model="claude-opus-5-5", max_tokens=10, messages=MSG)
    assert "sk-secret-123" not in (proxy.recorder.payload_dir / "r2.jsonl").read_text()


def test_openai_chat_stream_gets_usage_without_leaking_the_extra_chunk(proxy):
    client = openai_client(proxy, "r3")
    chunks = list(client.chat.completions.create(model="gpt-5", messages=MSG, stream=True))
    assert all(ch.choices for ch in chunks)  # the injected usage-only chunk is hidden from the agent
    assert "".join(ch.choices[0].delta.content or "" for ch in chunks) == "hello there"
    (call,) = proxy.recorder.collect("r3")
    assert call["usage"]["output"] == 7 and call["usage"]["input"] > 0
    assert call["response"]["choices"][0]["message"]["content"] == "hello there"


def test_openai_chat_stream_with_usage_requested_passes_it_through(proxy):
    client = openai_client(proxy, "r4")
    chunks = list(
        client.chat.completions.create(model="gpt-5", messages=MSG, stream=True, stream_options={"include_usage": True})
    )
    assert chunks[-1].usage is not None and chunks[-1].choices == []


def test_openai_responses_streaming_and_passthrough_endpoints(proxy):
    client = openai_client(proxy, "r5")
    with client.responses.stream(model="gpt-5", input="hi") as stream:
        final = stream.get_final_response()
    assert final.output_text == "the answer"
    assert client.models.list().data[0].id == "gpt-5"  # not recorded, just forwarded
    (call,) = proxy.recorder.collect("r5")
    assert call["api"] == "openai.responses"
    assert call["usage"] == {"input": 40, "cache_read": 10, "cache_write_5m": 0, "cache_write_1h": 0, "output": 3}


def test_spend_cap_returns_a_non_retried_error(mock_claude):
    server, _ = mock_claude
    with RecordingProxy(
        PriceTable(), spend_cap_usd=1e-9, upstreams={"anthropic": server.url, "openai": "x"}, port=0
    ) as p:
        client = anthropic_client(p, "r6")
        client.messages.create(model="claude-opus-5-5", max_tokens=10, messages=MSG)
        with pytest.raises(anthropic.BadRequestError, match="spend cap"):
            client.messages.create(model="claude-opus-5-5", max_tokens=10, messages=MSG)
        assert p.recorder.capped and "r6" in p.recorder.capped_runs
        assert len(p.recorder.collect("r6")) == 1


def test_upstream_errors_are_relayed_and_recorded(fake_openai):
    with RecordingProxy(PriceTable(), upstreams={"anthropic": fake_openai.url, "openai": fake_openai.url}, port=0) as p:
        r = httpx.post(f"{p.env_for('r7')['ANTHROPIC_BASE_URL']}/v1/messages", json={"model": "m", "messages": []})
        assert r.status_code == 404
        (call,) = p.recorder.collect("r7")
        assert call["status"] == 404 and call["usage"] is None


def test_classify_and_upstream_resolution():
    assert classify("anthropic", "POST", "v1/messages") == "anthropic.messages"
    assert classify("anthropic", "POST", "v1/messages/count_tokens") is None
    assert classify("openai", "POST", "v1/chat/completions") == "openai.chat"
    assert classify("openai", "GET", "v1/responses") is None
    up = resolve_upstreams(
        {"OPENAI_BASE_URL": "https://gw.example.com/openai/v1/", "ANTHROPIC_BASE_URL": "https://gw/a"}
    )
    assert up == {"anthropic": "https://gw/a", "openai": "https://gw.example.com/openai"}
    assert resolve_upstreams({})["anthropic"] == "https://api.anthropic.com"

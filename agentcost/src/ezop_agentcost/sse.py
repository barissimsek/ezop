"""Server-sent-event splitting and stream assembly for the three supported provider surfaces.

The proxy relays every event to the agent unchanged and feeds a copy to an assembler, which rebuilds the
non-streaming response body (content plus usage) for the recording.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass
class SSEEvent:
    raw: bytes
    event: str | None
    data: str

    def json(self) -> Any:
        try:
            return json.loads(self.data)
        except (ValueError, TypeError):
            return None


def parse_event(raw: bytes) -> SSEEvent:
    event: str | None = None
    data_lines: list[str] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip(" "))
    return SSEEvent(raw=raw, event=event, data="\n".join(data_lines))


def _find_boundary(buf: bytes) -> tuple[int, int]:
    """Return (index, separator length) of the first blank-line event terminator, or (-1, 0)."""
    best, size = -1, 0
    for sep in (b"\r\n\r\n", b"\n\n", b"\r\r"):
        i = buf.find(sep)
        if i != -1 and (best == -1 or i < best):
            best, size = i, len(sep)
    return best, size


async def iter_sse(chunks: AsyncIterator[bytes]) -> AsyncIterator[SSEEvent]:
    """Split a byte stream into events. Each event keeps its raw bytes, terminator included, for exact relay."""
    buf = b""
    async for chunk in chunks:
        buf += chunk
        while True:
            i, size = _find_boundary(buf)
            if i == -1:
                break
            raw, buf = buf[: i + size], buf[i + size :]
            yield parse_event(raw)
    if buf.strip():
        yield parse_event(buf)


class AnthropicStreamAssembler:
    """Rebuilds a Messages API ``message`` object from ``message_start`` / ``content_block_*`` / ``message_delta``."""

    def __init__(self) -> None:
        self.message: dict[str, Any] = {}
        self.blocks: dict[int, dict[str, Any]] = {}
        self.partial_json: dict[int, str] = {}
        self.usage: dict[str, Any] = {}
        self.error: Any = None

    def feed(self, ev: SSEEvent) -> None:
        data = ev.json()
        if not isinstance(data, dict):
            return
        kind = data.get("type") or ev.event
        if kind == "message_start":
            self.message = dict(data.get("message") or {})
            self.usage.update({k: v for k, v in (self.message.get("usage") or {}).items() if v is not None})
        elif kind == "content_block_start":
            self.blocks[data["index"]] = dict(data.get("content_block") or {})
        elif kind == "content_block_delta":
            block = self.blocks.setdefault(data["index"], {})
            delta = data.get("delta") or {}
            dtype = delta.get("type")
            if dtype == "text_delta":
                block["text"] = block.get("text", "") + delta.get("text", "")
            elif dtype == "input_json_delta":
                self.partial_json[data["index"]] = self.partial_json.get(data["index"], "") + delta.get(
                    "partial_json", ""
                )
            elif dtype == "thinking_delta":
                block["thinking"] = block.get("thinking", "") + delta.get("thinking", "")
            elif dtype == "signature_delta":
                block["signature"] = block.get("signature", "") + delta.get("signature", "")
        elif kind == "content_block_stop":
            idx = data["index"]
            if idx in self.partial_json:
                try:
                    self.blocks[idx]["input"] = json.loads(self.partial_json[idx] or "{}")
                except ValueError:
                    self.blocks[idx]["input"] = {"_unparsed": self.partial_json[idx]}
        elif kind == "message_delta":
            self.message.update({k: v for k, v in (data.get("delta") or {}).items() if v is not None})
            # message_delta usage is cumulative; later non-null values win.
            self.usage.update({k: v for k, v in (data.get("usage") or {}).items() if v is not None})
        elif kind == "error":
            self.error = data.get("error")

    def result(self) -> dict[str, Any]:
        msg = dict(self.message)
        msg["content"] = [self.blocks[i] for i in sorted(self.blocks)]
        msg["usage"] = self.usage
        return msg

    def usage_payload(self) -> dict[str, Any] | None:
        return self.usage or None


class OpenAIChatStreamAssembler:
    """Rebuilds a Chat Completions response from ``chat.completion.chunk`` events."""

    def __init__(self) -> None:
        self.id: str | None = None
        self.model: str | None = None
        self.choices: dict[int, dict[str, Any]] = {}
        self.usage: dict[str, Any] | None = None
        self.error: Any = None

    @staticmethod
    def is_usage_only(ev: SSEEvent) -> bool:
        data = ev.json()
        return isinstance(data, dict) and not data.get("choices") and data.get("usage") is not None

    def feed(self, ev: SSEEvent) -> None:
        if ev.data.strip() == "[DONE]":
            return
        data = ev.json()
        if not isinstance(data, dict):
            return
        if "error" in data:
            self.error = data["error"]
        self.id = self.id or data.get("id")
        self.model = self.model or data.get("model")
        if data.get("usage"):
            self.usage = data["usage"]
        for ch in data.get("choices") or []:
            choice = self.choices.setdefault(ch.get("index", 0), {"message": {"role": "assistant"}, "tool_calls": {}})
            delta = ch.get("delta") or {}
            msg = choice["message"]
            if delta.get("content"):
                msg["content"] = (msg.get("content") or "") + delta["content"]
            if delta.get("refusal"):
                msg["refusal"] = (msg.get("refusal") or "") + delta["refusal"]
            for tc in delta.get("tool_calls") or []:
                slot = choice["tool_calls"].setdefault(
                    tc.get("index", 0), {"id": None, "type": "function", "function": {"name": "", "arguments": ""}}
                )
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]
            if ch.get("finish_reason"):
                choice["finish_reason"] = ch["finish_reason"]

    def result(self) -> dict[str, Any]:
        choices = []
        for idx in sorted(self.choices):
            c = self.choices[idx]
            msg = dict(c["message"])
            if c["tool_calls"]:
                msg["tool_calls"] = [c["tool_calls"][i] for i in sorted(c["tool_calls"])]
            choices.append({"index": idx, "message": msg, "finish_reason": c.get("finish_reason")})
        return {
            "id": self.id,
            "object": "chat.completion",
            "model": self.model,
            "choices": choices,
            "usage": self.usage,
        }

    def usage_payload(self) -> dict[str, Any] | None:
        return self.usage


class OpenAIResponsesStreamAssembler:
    """The Responses API sends the complete response object in its terminal event."""

    TERMINAL = ("response.completed", "response.incomplete", "response.failed")

    def __init__(self) -> None:
        self.response: dict[str, Any] = {}
        self.error: Any = None

    def feed(self, ev: SSEEvent) -> None:
        data = ev.json()
        if not isinstance(data, dict):
            return
        kind = data.get("type") or ev.event
        if kind in ("response.created", "response.in_progress") and not self.response:
            self.response = dict(data.get("response") or {})
        elif kind in self.TERMINAL:
            self.response = dict(data.get("response") or {})
        elif kind == "error":
            self.error = data

    def result(self) -> dict[str, Any]:
        return self.response

    def usage_payload(self) -> dict[str, Any] | None:
        return self.response.get("usage") if self.response else None


def make_assembler(api: str) -> Any:
    return {
        "anthropic.messages": AnthropicStreamAssembler,
        "openai.chat": OpenAIChatStreamAssembler,
        "openai.responses": OpenAIResponsesStreamAssembler,
    }[api]()

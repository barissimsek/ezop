"""Offline stand-in for the Claude Messages API, scripted for the support agent.

It lets the seeded-regression benchmark (and agentcost's own CI) run end to end with no API key and no spend:

* scripted behavior: look up the order, then the customer, search the KB, check the refund policy, open a ticket
  when the policy asks for one, then answer; refinement prompts get a revised answer
* billing: its own tokenizer (deliberately different from ezop_agentcost's local counts), framing overhead, and prompt
  caching with breakpoints, a 1024-token minimum, and per-model cache namespaces
* streaming and non-streaming responses, plus ``/v1/messages/count_tokens``

Run standalone with ``python mock_claude.py --port 8900`` and point agentcost at it with
``AGENTCOST_ANTHROPIC_UPSTREAM=http://127.0.0.1:8900``.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import random
import re
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

MIN_CACHEABLE = 1024
REFINE_MARKER = "Review your draft reply"
FILLER = [
    "We want your next trip to go smoothly, so we will keep an eye on this until it is settled.",
    "If anything else comes up with this order, reply to this message and it will reach the same team.",
    "Thanks for giving us the chance to make this right.",
    "You will get an email confirmation as soon as the change is processed.",
]


def mock_tokens(text: str) -> int:
    return math.ceil(len(text) / 3.6) if text else 0


def _render_blocks(body: dict[str, Any]) -> list[tuple[str, bool]]:
    """The prompt as (text, is_cache_breakpoint) pieces in render order: tools, system, messages."""
    out: list[tuple[str, bool]] = []
    tools = body.get("tools") or []
    if tools:
        stable = [{k: t.get(k) for k in ("name", "description", "input_schema")} for t in tools]
        out.append((json.dumps(stable, sort_keys=True), bool(tools[-1].get("cache_control"))))
    system = body.get("system")
    if isinstance(system, str):
        out.append((system, False))
    for b in system or [] if not isinstance(system, str) else []:
        out.append((b.get("text", ""), bool(b.get("cache_control"))))
    for msg in body.get("messages") or []:
        content = msg["content"]
        if isinstance(content, str):
            out.append((f"<{msg['role']}>" + content, False))
            continue
        for b in content:
            t = b.get("type")
            if t == "text":
                text = b.get("text", "")
            elif t == "tool_use":
                text = json.dumps({"name": b.get("name"), "input": b.get("input")}, sort_keys=True)
            elif t == "tool_result":
                c = b.get("content")
                text = c if isinstance(c, str) else json.dumps(c, sort_keys=True)
            else:
                text = ""
            out.append((f"<{msg['role']}>" + text, bool(b.get("cache_control"))))
    if body.get("cache_control") and out:
        out[-1] = (out[-1][0], True)
    return out


class MockClaude:
    def __init__(self, noise: float = 0.3, seed: int | None = None):
        self.noise = noise
        self.rng = random.Random(seed)
        self.cache: set[str] = set()
        self.ids = itertools.count(1)

    # -- billing

    def usage(self, body: dict[str, Any]) -> dict[str, int]:
        blocks = _render_blocks(body)
        model = body.get("model", "")
        h = hashlib.sha256(model.encode())
        # Framing sits where the real API renders it: the request preamble (and the tool-use system prompt) ahead
        # of everything, so inside the cached prefix, and a few role-marker tokens per message.
        cum = 10 + (250 if body.get("tools") else 0)
        breakpoints: list[tuple[int, str]] = []
        last_role = None
        for text, bp in blocks:
            role = text[1 : text.index(">")] if text.startswith("<") and ">" in text else None
            if role and role != last_role:
                cum += 3
            last_role = role or last_role
            cum += mock_tokens(text)
            h.update(text.encode() + b"\x00")
            if bp:
                breakpoints.append((cum, h.copy().hexdigest()))
        total = cum
        read = write = 0
        for tokens, key in reversed(breakpoints):
            if key in self.cache and tokens >= MIN_CACHEABLE:
                read = tokens
                break
        if breakpoints:
            last_tokens, last_key = breakpoints[-1]
            if last_tokens >= MIN_CACHEABLE and last_key not in self.cache:
                write = last_tokens - read
            for tokens, key in breakpoints:
                if tokens >= MIN_CACHEABLE:
                    self.cache.add(key)
        return {
            "input_tokens": total - read - write,
            "cache_read_input_tokens": read,
            "cache_creation_input_tokens": write,
        }

    # -- behavior

    def respond(self, body: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        messages = body.get("messages") or []
        first = messages[0]["content"] if messages else ""
        first = (
            first if isinstance(first, str) else " ".join(b.get("text", "") for b in first if b.get("type") == "text")
        )
        last = messages[-1]["content"] if messages else ""
        calls: dict[str, dict[str, Any]] = {}
        results: dict[str, Any] = {}
        for msg in messages:
            if isinstance(msg["content"], str):
                continue
            for b in msg["content"]:
                if b.get("type") == "tool_use":
                    calls[b["id"]] = b
                elif b.get("type") == "tool_result":
                    try:
                        results[calls[b["tool_use_id"]]["name"]] = json.loads(b["content"])
                    except (KeyError, ValueError, TypeError):
                        pass
        done = {c["name"] for c in calls.values()}
        order_id = (re.search(r"\b(1\d{3})\b", first) or re.search(r"(\d+)", first or "0")).group(1)

        if isinstance(last, str) and last.startswith(REFINE_MARKER):
            return [{"type": "text", "text": self.answer(first, order_id, results, revised=True)}], "end_turn"

        def tool(name: str, args: dict[str, Any], lead: str) -> tuple[list[dict[str, Any]], str]:
            return [
                {"type": "text", "text": lead},
                {"type": "tool_use", "id": f"toolu_mock_{next(self.ids):06d}", "name": name, "input": args},
            ], "tool_use"

        if "lookup_order" not in done:
            return tool("lookup_order", {"order_id": order_id}, f"Let me pull up order {order_id}.")
        order = results.get("lookup_order") or {}
        if "lookup_customer" not in done and order.get("customer_email"):
            return tool("lookup_customer", {"email": order["customer_email"]}, "Checking the customer profile.")
        if "search_kb" not in done:
            return tool("search_kb", {"query": first[:120]}, "Searching the knowledge base.")
        if "check_refund_policy" not in done:
            return tool("check_refund_policy", {"order_id": order_id, "reason": first[:80]}, "Checking eligibility.")
        policy = results.get("check_refund_policy") or {}
        if policy.get("requires_ticket") and "create_ticket" not in done:
            return tool(
                "create_ticket",
                {"order_id": order_id, "summary": f"Warranty review for order {order_id}: {first[:80]}"},
                "Opening a ticket for the warranty team.",
            )
        return [{"type": "text", "text": self.answer(first, order_id, results)}], "end_turn"

    def answer(self, first: str, order_id: str, results: dict[str, Any], revised: bool = False) -> str:
        customer = results.get("lookup_customer") or {}
        name = (customer.get("name") or "there").split()[0]
        kb = results.get("search_kb") or [{}]
        policy = results.get("check_refund_policy") or {}
        ticket = results.get("create_ticket") or {}
        decision = "is eligible for a refund" if policy.get("eligible") else "is not eligible for a refund yet"
        parts = [
            f"Hi {name}, thanks for reaching out about order {order_id}.",
            f"Following our guidance on {str(kb[0].get('title', 'your request')).lower()}, your order {decision}"
            f" because it is {policy.get('why', 'under review')}.",
        ]
        if ticket:
            parts.append(f"I opened ticket {ticket.get('ticket_id')} so the warranty team can take a look.")
        seed = int(hashlib.sha1(first.encode()).hexdigest(), 16)
        n_fill = 1 + seed % 3 + (1 if self.rng.random() < self.noise else 0)
        parts.extend(FILLER[(seed + i) % len(FILLER)] for i in range(n_fill))
        if revised:
            parts.append("Let us know if there is anything else we can help with.")
        return " ".join(parts)

    # -- HTTP

    def message(self, body: dict[str, Any]) -> dict[str, Any]:
        content, stop = self.respond(body)
        usage = self.usage(body)
        out_text = "".join(b.get("text", "") + json.dumps(b.get("input", "")) for b in content)
        usage["output_tokens"] = mock_tokens(out_text)
        return {
            "id": f"msg_mock_{next(self.ids):06d}",
            "type": "message",
            "role": "assistant",
            "model": body.get("model"),
            "content": content,
            "stop_reason": stop,
            "stop_sequence": None,
            "usage": usage,
        }


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def _stream_events(msg: dict[str, Any]) -> list[bytes]:
    usage = msg["usage"]
    start = {**msg, "content": [], "stop_reason": None, "usage": {**usage, "output_tokens": 1}}
    events = [_sse("message_start", {"type": "message_start", "message": start})]
    for i, block in enumerate(msg["content"]):
        if block["type"] == "text":
            events.append(
                _sse(
                    "content_block_start",
                    {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}},
                )
            )
            text = block["text"]
            for j in range(0, len(text), 40):
                events.append(
                    _sse(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": i,
                            "delta": {"type": "text_delta", "text": text[j : j + 40]},
                        },
                    )
                )
        else:
            events.append(
                _sse(
                    "content_block_start",
                    {"type": "content_block_start", "index": i, "content_block": {**block, "input": {}}},
                )
            )
            events.append(
                _sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": i,
                        "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])},
                    },
                )
            )
        events.append(_sse("content_block_stop", {"type": "content_block_stop", "index": i}))
    events.append(
        _sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": msg["stop_reason"], "stop_sequence": None},
                "usage": {"output_tokens": usage["output_tokens"]},
            },
        )
    )
    events.append(_sse("message_stop", {"type": "message_stop"}))
    return events


def create_app(noise: float | None = None, seed: int | None = None) -> Starlette:
    mock = MockClaude(noise=float(os.environ.get("MOCK_NOISE", 0.3)) if noise is None else noise, seed=seed)

    async def messages(request: Request) -> Response:
        body = await request.json()
        msg = mock.message(body)
        if body.get("stream"):
            events = _stream_events(msg)

            async def gen():  # type: ignore[no-untyped-def]
                for e in events:
                    yield e

            return StreamingResponse(gen(), media_type="text/event-stream")
        return JSONResponse(msg)

    async def count_tokens(request: Request) -> Response:
        body = await request.json()
        usage = MockClaude(noise=0).usage(body)  # a fresh instance: counting must not touch the cache
        return JSONResponse({"input_tokens": sum(usage.values())})

    app = Starlette(
        routes=[
            Route("/v1/messages", messages, methods=["POST"]),
            Route("/v1/messages/count_tokens", count_tokens, methods=["POST"]),
        ]
    )
    app.state.mock = mock
    return app


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8900)
    parser.add_argument("--noise", type=float, default=0.3)
    args = parser.parse_args()
    uvicorn.run(create_app(noise=args.noise), host="127.0.0.1", port=args.port, log_level="warning")

"""Minimal OpenAI stand-in for proxy tests: Chat Completions and Responses, streaming and not."""

from __future__ import annotations

import json
from itertools import count
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route


def create_app() -> Starlette:
    ids = count(1)

    async def chat(request: Request) -> Response:
        body = await request.json()
        n_in = sum(len(json.dumps(m)) // 4 for m in body["messages"])
        usage = {"prompt_tokens": n_in, "completion_tokens": 7, "prompt_tokens_details": {"cached_tokens": 0}}
        cid = f"chatcmpl-{next(ids)}"
        if not body.get("stream"):
            return JSONResponse(
                {
                    "id": cid,
                    "object": "chat.completion",
                    "created": 0,
                    "model": body["model"],
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "hello there"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": usage,
                }
            )

        def chunk(delta: dict[str, Any], finish: str | None = None) -> bytes:
            data = {
                "id": cid,
                "object": "chat.completion.chunk",
                "created": 0,
                "model": body["model"],
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            return f"data: {json.dumps(data)}\n\n".encode()

        async def gen():  # type: ignore[no-untyped-def]
            yield chunk({"role": "assistant", "content": "hello"})
            yield chunk({"content": " there"})
            yield chunk({}, "stop")
            if (body.get("stream_options") or {}).get("include_usage"):
                tail = {"id": cid, "object": "chat.completion.chunk", "created": 0, "model": body["model"],
                        "choices": [], "usage": usage}  # fmt: skip
                yield f"data: {json.dumps(tail)}\n\n".encode()
            yield b"data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    async def responses(request: Request) -> Response:
        body = await request.json()
        rid = f"resp_{next(ids)}"
        resp = {
            "id": rid,
            "object": "response",
            "model": body["model"],
            "status": "completed",
            "output": [
                {"type": "message", "id": f"msg_{rid}", "role": "assistant", "status": "completed",
                 "content": [{"type": "output_text", "text": "the answer", "annotations": []}]}
            ],
            "usage": {"input_tokens": 50, "input_tokens_details": {"cached_tokens": 10}, "output_tokens": 3,
                      "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 53},
        }  # fmt: skip
        if not body.get("stream"):
            return JSONResponse(resp)

        async def gen():  # type: ignore[no-untyped-def]
            created = {**resp, "status": "in_progress", "output": [], "usage": None}
            yield f"event: response.created\ndata: {json.dumps({'type': 'response.created', 'response': created})}\n\n".encode()
            done = {"type": "response.completed", "response": resp}
            yield f"event: response.completed\ndata: {json.dumps(done)}\n\n".encode()

        return StreamingResponse(gen(), media_type="text/event-stream")

    async def models(request: Request) -> Response:
        return JSONResponse({"object": "list", "data": [{"id": "gpt-5", "object": "model"}]})

    return Starlette(
        routes=[
            Route("/v1/chat/completions", chat, methods=["POST"]),
            Route("/v1/responses", responses, methods=["POST"]),
            Route("/v1/models", models),
        ]
    )

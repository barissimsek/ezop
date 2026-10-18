"""Local recording proxy.

The agent talks to ``http://127.0.0.1:<port>/run/<run_id>/<provider>/...`` instead of the provider. The proxy strips
the prefix, forwards the request unchanged (API key included, never stored), relays the response (streamed chunks
are passed through as they arrive), and records request + response + billed usage for the run.

    agent  ->  127.0.0.1:8787/run/<run_id>/anthropic  ->  api.anthropic.com
    agent  ->  127.0.0.1:8787/run/<run_id>/openai/v1  ->  api.openai.com/v1
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from ezop_agentcost.pricing import ModelPrice, PriceTable
from ezop_agentcost.sse import OpenAIChatStreamAssembler, iter_sse, make_assembler
from ezop_agentcost.usage import Usage

log = logging.getLogger("ezop_agentcost.proxy")

DEFAULT_UPSTREAMS = {"anthropic": "https://api.anthropic.com", "openai": "https://api.openai.com"}

# Price used for spend-cap accounting only, when a model is missing from the price table. Deliberately high.
_CAP_FALLBACK_PRICE = ModelPrice(input=15.0, output=75.0, cache_read=1.5, cache_write_5m=18.75, cache_write_1h=30.0)

_DROP_REQUEST_HEADERS = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "accept-encoding",
}
_DROP_RESPONSE_HEADERS = {"content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive"}


def classify(provider: str, method: str, path: str) -> str | None:
    """Return the recorded API surface for a request path, or None for pass-through endpoints."""
    if method != "POST":
        return None
    p = path.strip("/")
    if provider == "anthropic" and p == "v1/messages":
        return "anthropic.messages"
    if provider == "openai" and p == "v1/chat/completions":
        return "openai.chat"
    if provider == "openai" and p == "v1/responses":
        return "openai.responses"
    return None


def normalize_usage(api: str, payload: dict[str, Any] | None) -> Usage | None:
    if not payload:
        return None
    if api == "anthropic.messages":
        return Usage.from_anthropic(payload)
    if api == "openai.chat":
        return Usage.from_openai_chat(payload)
    if api == "openai.responses":
        return Usage.from_openai_responses(payload)
    return None


def resolve_upstreams(env: dict[str, str] | None = None) -> dict[str, str]:
    """Where the proxy forwards to. A pre-existing ``ANTHROPIC_BASE_URL`` / ``OPENAI_BASE_URL`` (a corporate
    gateway, say) is honored, so agentcost sits in front of it rather than bypassing it."""
    env = dict(os.environ if env is None else env)
    anthropic = (
        env.get("AGENTCOST_ANTHROPIC_UPSTREAM") or env.get("ANTHROPIC_BASE_URL") or DEFAULT_UPSTREAMS["anthropic"]
    )
    openai = env.get("AGENTCOST_OPENAI_UPSTREAM") or env.get("OPENAI_BASE_URL") or DEFAULT_UPSTREAMS["openai"]
    openai = openai.rstrip("/")
    if openai.endswith("/v1"):
        openai = openai[:-3]
    return {"anthropic": anthropic.rstrip("/"), "openai": openai}


class Recorder:
    """Thread-safe store of recorded calls, keyed by run id. Optionally mirrors each call to ``<run_id>.jsonl``."""

    def __init__(self, prices: PriceTable, spend_cap_usd: float | None = None, payload_dir: Path | None = None):
        self.prices = prices
        self.spend_cap_usd = spend_cap_usd
        self.payload_dir = payload_dir
        self.spent_usd = 0.0
        self.capped = False
        self.capped_runs: set[str] = set()
        self._calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._seq: dict[str, int] = defaultdict(int)
        self._inflight: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        if payload_dir:
            payload_dir.mkdir(parents=True, exist_ok=True)

    def cap_reached(self) -> bool:
        with self._lock:
            return self.spend_cap_usd is not None and self.spent_usd >= self.spend_cap_usd

    def mark_capped(self, run_id: str) -> None:
        with self._lock:
            self.capped = True
            self.capped_runs.add(run_id)

    def begin(self, run_id: str) -> int:
        with self._lock:
            self._seq[run_id] += 1
            self._inflight[run_id] += 1
            return self._seq[run_id]

    def finish(self, record: dict[str, Any]) -> None:
        usage = Usage.from_dict(record["usage"]) if record.get("usage") else None
        cost = 0.0
        if usage is not None:
            price = self.prices.lookup(record.get("model") or "") or _CAP_FALLBACK_PRICE
            cost = price.cost(usage)
        with self._lock:
            self.spent_usd += cost
            self._calls[record["run_id"]].append(record)
            self._inflight[record["run_id"]] -= 1
        if self.payload_dir:
            with open(self.payload_dir / f"{record['run_id']}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

    def collect(self, run_id: str, wait_s: float = 5.0) -> list[dict[str, Any]]:
        """Calls for a run, in call order. Waits briefly for streams the agent finished reading but the proxy has
        not finished recording."""
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            with self._lock:
                if self._inflight[run_id] <= 0:
                    break
            time.sleep(0.02)
        with self._lock:
            return sorted(self._calls.get(run_id, []), key=lambda r: r["seq"])


def _cap_error(provider: str, cap: float | None) -> Response:
    msg = f"agentcost: spend cap of ${cap:.2f} reached for this check; request not sent."
    if provider == "anthropic":
        body: dict[str, Any] = {"type": "error", "error": {"type": "invalid_request_error", "message": msg}}
    else:
        body = {"error": {"message": msg, "type": "invalid_request_error", "code": "agentcost_spend_cap"}}
    # 400 so SDK retry logic does not hammer the cap.
    return JSONResponse(body, status_code=400)


def build_app(recorder: Recorder, upstreams: dict[str, str], timeout_s: float = 600.0) -> Starlette:
    state: dict[str, httpx.AsyncClient] = {}

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        state["client"] = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=30.0), follow_redirects=False)
        yield
        await state["client"].aclose()

    async def handle(request: Request) -> Response:
        run_id = request.path_params["run_id"]
        provider = request.path_params["provider"]
        path = request.path_params["path"]
        if provider not in upstreams:
            return JSONResponse({"error": f"agentcost: unknown provider '{provider}'"}, status_code=404)
        body = await request.body()
        url = f"{upstreams[provider]}/{path}"
        if request.url.query:
            url += f"?{request.url.query}"
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP_REQUEST_HEADERS}
        headers["accept-encoding"] = "identity"
        client = state["client"]
        api = classify(provider, request.method, path)

        if api is None:
            up = await client.request(request.method, url, headers=headers, content=body)
            return Response(up.content, status_code=up.status_code, headers=_response_headers(up))

        try:
            req_json: Any = json.loads(body) if body else {}
        except ValueError:
            req_json = None
        if recorder.cap_reached():
            recorder.mark_capped(run_id)
            return _cap_error(provider, recorder.spend_cap_usd)

        streaming = isinstance(req_json, dict) and bool(req_json.get("stream"))
        strip_usage_chunk = False
        if api == "openai.chat" and streaming:
            # Chat Completions streams carry usage only when asked. Ask for it, then hide that extra chunk from an
            # agent that did not request it, so its own chunk handling is unaffected.
            opts = req_json.get("stream_options") or {}
            if not opts.get("include_usage"):
                req_json["stream_options"] = {**opts, "include_usage": True}
                body = json.dumps(req_json).encode()
                strip_usage_chunk = True

        seq = recorder.begin(run_id)
        started = time.monotonic()
        record: dict[str, Any] = {
            "run_id": run_id,
            "seq": seq,
            "provider": provider,
            "api": api,
            "model": req_json.get("model") if isinstance(req_json, dict) else None,
            "streamed": streaming,
            "request": req_json,
            "response": None,
            "usage": None,
            "status": None,
            "error": None,
            "latency_ms": None,
        }

        def finish(status: int, response: Any, usage_payload: dict[str, Any] | None, error: Any = None) -> None:
            record["status"] = status
            record["response"] = response
            record["error"] = error
            record["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            if isinstance(response, dict) and response.get("model"):
                record["response_model"] = response["model"]
            usage = normalize_usage(api, usage_payload) if status < 400 else None
            record["usage"] = usage.to_dict() if usage else None
            recorder.finish(record)

        try:
            up_req = client.build_request(request.method, url, headers=headers, content=body)
            up = await client.send(up_req, stream=True)
        except httpx.HTTPError as e:
            finish(502, None, None, error=f"upstream error: {e!r}")
            return JSONResponse({"error": f"agentcost proxy: upstream error: {e!r}"}, status_code=502)

        content_type = up.headers.get("content-type", "")
        if "text/event-stream" not in content_type:
            try:
                content = await up.aread()
            finally:
                await up.aclose()
            try:
                resp_json = json.loads(content) if content else None
            except ValueError:
                resp_json = None
            usage_payload = resp_json.get("usage") if isinstance(resp_json, dict) else None
            error = resp_json if up.status_code >= 400 else None
            finish(up.status_code, resp_json, usage_payload, error=error)
            return Response(content, status_code=up.status_code, headers=_response_headers(up))

        assembler = make_assembler(api)

        async def relay() -> AsyncIterator[bytes]:
            error: Any = None
            try:
                async for ev in iter_sse(up.aiter_bytes()):
                    assembler.feed(ev)
                    if strip_usage_chunk and OpenAIChatStreamAssembler.is_usage_only(ev):
                        continue
                    yield ev.raw
            except BaseException as e:  # client disconnect surfaces as cancellation
                error = f"stream interrupted: {e!r}"
                raise
            finally:
                await up.aclose()
                finish(up.status_code, assembler.result(), assembler.usage_payload(), error=error or assembler.error)

        return StreamingResponse(relay(), status_code=up.status_code, headers=_response_headers(up))

    async def health(request: Request) -> Response:
        return JSONResponse({"ok": True, "spent_usd": recorder.spent_usd})

    methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    return Starlette(
        routes=[
            Route("/_agentcost/health", health),
            Route("/run/{run_id}/{provider}/{path:path}", handle, methods=methods),
        ],
        lifespan=lifespan,
    )


def _response_headers(up: httpx.Response) -> dict[str, str]:
    return {k: v for k, v in up.headers.items() if k.lower() not in _DROP_RESPONSE_HEADERS}


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


class ServerThread:
    """Runs an ASGI app with uvicorn on a background thread."""

    def __init__(self, app: Any, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port if port and _port_free(host, port) else free_port(host)
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning", lifespan="on")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True, name=f"agentcost-server-{self.port}")

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> ServerThread:
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline or not self.thread.is_alive():
                raise RuntimeError(f"server failed to start on {self.url}")
            time.sleep(0.01)
        return self

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

    def __enter__(self) -> ServerThread:
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()


class RecordingProxy:
    """The recording proxy for one check. Use as a context manager."""

    def __init__(
        self,
        prices: PriceTable,
        spend_cap_usd: float | None = None,
        payload_dir: Path | None = None,
        upstreams: dict[str, str] | None = None,
        port: int = 8787,
    ):
        self.recorder = Recorder(prices, spend_cap_usd, payload_dir)
        self.upstreams = upstreams or resolve_upstreams()
        self._server = ServerThread(build_app(self.recorder, self.upstreams), port=port)

    @property
    def url(self) -> str:
        return self._server.url

    def env_for(self, run_id: str) -> dict[str, str]:
        """Environment variables that point the official SDKs at this proxy for one run."""
        return {
            "ANTHROPIC_BASE_URL": f"{self.url}/run/{run_id}/anthropic",
            "OPENAI_BASE_URL": f"{self.url}/run/{run_id}/openai/v1",
            "AGENTCOST_RUN_ID": run_id,
        }

    def __enter__(self) -> RecordingProxy:
        self._server.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._server.stop()

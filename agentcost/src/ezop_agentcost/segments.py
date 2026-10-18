"""Segmentation: split every recorded call's prompt into segments with keys that are stable across runs.

=========================  =====================================================================
key                        content
=========================  =====================================================================
``tool_schemas``           tool definitions sent with the call
``system_prompt``          system message / Responses ``instructions``
``system_message#n``       mid-conversation system or developer messages
``user_input``             the first user message of the run (the fixture's task)
``user_message#n``         later user messages (refinement prompts, sub-agent tasks, ...)
``tool_result:<name>#<n>`` the n-th distinct result of tool ``<name>`` in the run
``assistant_turn#<n>``     model output carried forward, produced by the run's n-th call
``mutated``                content a framework rewrote (summarized, truncated) and can't be matched
``overhead``               framing tokens the provider adds (role markers, tool-use preamble)
=========================  =====================================================================

A *family* is a key without its ``#n`` suffix. Billed input tokens are allocated to segments by local token count,
scaled so each call's segments sum exactly to its billed input. Cache-read tokens are assigned to the leading
segments (the cached prefix), cache-write tokens to the segments right after them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from ezop_agentcost.tokens import TokenCounter
from ezop_agentcost.usage import Usage

IMAGE_TOKENS = 1000  # flat estimate for images and documents; replaced by scaling to billed totals


@dataclass
class Block:
    kind: str  # tools | system | system_message | user | assistant | tool_result
    text: str
    canon: str
    ref: str | None = None
    name: str | None = None
    tool_calls: list[tuple[str | None, str | None]] = field(default_factory=list)  # (call id, tool name)
    fixed_tokens: int = 0

    @property
    def digest(self) -> str:
        return hashlib.sha1(f"{self.kind}\x00{self.canon}".encode()).hexdigest()


def family_of(key: str) -> str:
    return key.split("#", 1)[0]


def _jdump(v: Any) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _strip_meta(block: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in block.items() if k not in ("cache_control", "citations")}


def _norm_args(args: Any) -> str:
    if isinstance(args, str):
        try:
            return _jdump(json.loads(args))
        except ValueError:
            return args
    return _jdump(args)


# --------------------------------------------------------------------------------------------------- Anthropic


def _anthropic_assistant(content: Any) -> Block:
    if isinstance(content, str):
        return Block("assistant", content, "T:" + content)
    canon: list[str] = []
    text: list[str] = []
    calls: list[tuple[str | None, str | None]] = []
    for b in content or []:
        t = b.get("type")
        if t == "text":
            if b.get("text"):
                canon.append("T:" + b["text"])
                text.append(b["text"])
        elif t in ("tool_use", "server_tool_use"):
            args = _jdump(b.get("input") or {})
            canon.append(f"U:{b.get('name')}:{args}")
            text.append(f"{b.get('name')} {args}")
            calls.append((b.get("id"), b.get("name")))
        elif t == "thinking":
            canon.append("R:" + (b.get("thinking") or ""))
            text.append(b.get("thinking") or "")
        elif t == "redacted_thinking":
            canon.append("R*:" + (b.get("data") or "")[:64])
        else:
            dumped = _jdump(_strip_meta(b))
            canon.append(f"{t}:{dumped}")
            text.append(dumped)
    return Block("assistant", "\n".join(text), "\n".join(canon), tool_calls=calls)


def _anthropic_tool_result_text(content: Any) -> tuple[str, int]:
    if isinstance(content, str):
        return content, 0
    texts, fixed = [], 0
    for b in content or []:
        if b.get("type") == "text":
            texts.append(b.get("text") or "")
        elif b.get("type") in ("image", "document"):
            fixed += IMAGE_TOKENS
        else:
            texts.append(_jdump(_strip_meta(b)))
    return "\n".join(texts), fixed


def anthropic_request_blocks(req: dict[str, Any]) -> list[Block]:
    blocks: list[Block] = []
    if req.get("tools"):
        tools = [_strip_meta(t) for t in req["tools"]]
        blocks.append(Block("tools", _jdump(tools), _jdump(tools)))
    system = req.get("system")
    if system:
        text = system if isinstance(system, str) else "\n".join(b.get("text", "") for b in system)
        blocks.append(Block("system", text, text))
    for msg in req.get("messages") or []:
        role, content = msg.get("role"), msg.get("content")
        if role == "assistant":
            blocks.append(_anthropic_assistant(content))
            continue
        if role == "system":
            text = content if isinstance(content, str) else "\n".join(b.get("text", "") for b in content or [])
            blocks.append(Block("system_message", text, text))
            continue
        if isinstance(content, str):
            blocks.append(Block("user", content, content))
            continue
        pending_text: list[str] = []
        pending_fixed = 0

        def flush() -> None:
            nonlocal pending_text, pending_fixed
            if pending_text or pending_fixed:
                t = "\n".join(pending_text)
                blocks.append(Block("user", t, t + f"\x00img{pending_fixed}", fixed_tokens=pending_fixed))
            pending_text, pending_fixed = [], 0

        for b in content or []:
            t = b.get("type")
            if t == "tool_result":
                flush()
                text, fixed = _anthropic_tool_result_text(b.get("content"))
                blocks.append(
                    Block(
                        "tool_result",
                        text,
                        text + f"\x00err={bool(b.get('is_error'))}",
                        ref=b.get("tool_use_id"),
                        fixed_tokens=fixed,
                    )
                )
            elif t == "text":
                pending_text.append(b.get("text") or "")
            elif t in ("image", "document"):
                pending_fixed += IMAGE_TOKENS
            else:
                pending_text.append(_jdump(_strip_meta(b)))
        flush()
    return blocks


def anthropic_response_blocks(resp: dict[str, Any]) -> list[Block]:
    if not isinstance(resp, dict) or "content" not in resp:
        return []
    return [_anthropic_assistant(resp.get("content"))]


# --------------------------------------------------------------------------------------------- OpenAI Chat


def _parts_text(content: Any) -> tuple[str, int]:
    if content is None:
        return "", 0
    if isinstance(content, str):
        return content, 0
    texts, fixed = [], 0
    for p in content:
        t = p.get("type")
        if t in ("text", "input_text", "output_text"):
            texts.append(p.get("text") or "")
        elif t in ("refusal",):
            texts.append(p.get("refusal") or "")
        elif t in ("image_url", "input_image", "input_audio", "file", "input_file"):
            fixed += IMAGE_TOKENS
        else:
            texts.append(_jdump(p))
    return "\n".join(texts), fixed


def _openai_assistant(msg: dict[str, Any]) -> Block:
    content, _ = _parts_text(msg.get("content"))
    canon: list[str] = ["T:" + content] if content else []
    text: list[str] = [content] if content else []
    calls: list[tuple[str | None, str | None]] = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        args = _norm_args(fn.get("arguments") or "")
        canon.append(f"U:{fn.get('name')}:{args}")
        text.append(f"{fn.get('name')} {fn.get('arguments') or ''}")
        calls.append((tc.get("id"), fn.get("name")))
    if msg.get("function_call"):
        fn = msg["function_call"]
        canon.append(f"U:{fn.get('name')}:{_norm_args(fn.get('arguments') or '')}")
        text.append(f"{fn.get('name')} {fn.get('arguments') or ''}")
    return Block("assistant", "\n".join(text), "\n".join(canon), tool_calls=calls)


def openai_chat_request_blocks(req: dict[str, Any]) -> list[Block]:
    blocks: list[Block] = []
    tools = req.get("tools") or req.get("functions")
    if tools:
        blocks.append(Block("tools", _jdump(tools), _jdump(tools)))
    for i, msg in enumerate(req.get("messages") or []):
        role = msg.get("role")
        if role in ("system", "developer"):
            text, _ = _parts_text(msg.get("content"))
            blocks.append(Block("system" if i == 0 else "system_message", text, text))
        elif role == "assistant":
            blocks.append(_openai_assistant(msg))
        elif role == "tool":
            text, fixed = _parts_text(msg.get("content"))
            blocks.append(Block("tool_result", text, text, ref=msg.get("tool_call_id"), fixed_tokens=fixed))
        elif role == "function":
            text, _ = _parts_text(msg.get("content"))
            blocks.append(Block("tool_result", text, text, name=msg.get("name")))
        else:
            text, fixed = _parts_text(msg.get("content"))
            blocks.append(Block("user", text, text + f"\x00img{fixed}", fixed_tokens=fixed))
    return blocks


def openai_chat_response_blocks(resp: dict[str, Any]) -> list[Block]:
    choices = resp.get("choices") if isinstance(resp, dict) else None
    if not choices:
        return []
    return [_openai_assistant(choices[0].get("message") or {})]


# ------------------------------------------------------------------------------------------ OpenAI Responses


def _responses_item(item: Any) -> Block:
    if isinstance(item, str):
        return Block("user", item, item)
    t = item.get("type") or ("message" if "role" in item else None)
    if t == "message":
        role = item.get("role")
        text, fixed = _parts_text(item.get("content"))
        if role == "assistant":
            return Block("assistant", text, "T:" + text)
        if role in ("system", "developer"):
            return Block("system_message", text, text)
        return Block("user", text, text + f"\x00img{fixed}", fixed_tokens=fixed)
    if t == "function_call":
        args = _norm_args(item.get("arguments") or "")
        return Block(
            "assistant",
            f"{item.get('name')} {item.get('arguments') or ''}",
            f"U:{item.get('name')}:{args}",
            tool_calls=[(item.get("call_id"), item.get("name"))],
        )
    if t == "function_call_output":
        out = item.get("output")
        text, fixed = _parts_text(out) if not isinstance(out, str) else (out, 0)
        return Block("tool_result", text, text, ref=item.get("call_id"), fixed_tokens=fixed)
    if t == "reasoning":
        summary = "\n".join(s.get("text", "") for s in item.get("summary") or [])
        return Block("assistant", summary, "R:" + (item.get("id") or summary))
    dumped = _jdump(item)
    return Block("assistant" if str(t).endswith("_call") else "user", dumped, f"{t}:{dumped}")


def responses_input_blocks(req: dict[str, Any]) -> list[Block]:
    inp = req.get("input")
    if inp is None:
        return []
    if isinstance(inp, str):
        return [Block("user", inp, inp)]
    return [_responses_item(it) for it in inp]


def responses_output_blocks(resp: dict[str, Any]) -> list[Block]:
    if not isinstance(resp, dict):
        return []
    return [_responses_item(it) for it in resp.get("output") or []]


# ------------------------------------------------------------------------------------------------- the run


@dataclass
class Segment:
    key: str
    tokens: float
    cache_read: float = 0.0
    cache_write: float = 0.0

    @property
    def family(self) -> str:
        return family_of(self.key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "tokens": round(self.tokens, 3),
            "cache_read": round(self.cache_read, 3),
            "cache_write": round(self.cache_write, 3),
        }


def with_overhead(api: str, blocks: list[Block], named: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Insert estimated framing tokens where the provider renders them, as ``overhead`` entries.

    The request preamble (and, for Anthropic, the tool-use system prompt) comes first, inside any cached prefix;
    role markers come before each message block. Positioning matters: cache zones are calibrated by position.
    """
    has_tools = any(b.kind == "tools" for b in blocks)
    if api == "anthropic.messages":
        preamble = 7 + (300 if has_tools else 0)
    else:
        preamble = 3 + (10 if has_tools else 0)
    out: list[tuple[str, int]] = [("overhead", preamble)]
    for b, item in zip(blocks, named):
        if b.kind not in ("tools", "system"):
            out.append(("overhead", 4))
        out.append(item)
    return out


MAX_ZONE_RATIO = 3.0  # local tokenizers drift ~±20% by content type (JSON vs prose); 3x is far past that


def zone_scales(local: list[float], target: float, read: float, write: float) -> list[float]:
    """Per-segment scale factors that make each cache zone sum to its billed amount.

    Anthropic cache reads and writes end at cache breakpoints, which sit at block boundaries. So the billed
    ``cache_read`` total is an exact count for the leading segments it covers, and ``cache_read + cache_write``
    for the segments up to the last breakpoint. Scaling each zone separately keeps tokenizer error in one part of
    the prompt (a large JSON tool result, say) from leaking into the stable prefix. A cut is used only when a
    segment boundary fits it.

    The boundary chosen for a cut is the one needing the least *differential* scaling between the zone before it
    and everything after it: the right boundary differs only by tokenizer drift between content types, while a
    wrong one pushes a whole segment across the line. A cut whose best boundary still needs more than
    ``MAX_ZONE_RATIO`` between the two sides is skipped.
    """
    n = len(local)
    total_local = sum(local)
    uniform = target / total_local
    prefix = [0.0]
    for x in local:
        prefix.append(prefix[-1] + x)
    cuts: list[tuple[int, float]] = [(0, 0.0)]
    for t in (read, read + write):
        prev_k, prev_t = cuts[-1]
        if t - prev_t <= 0 or t >= target - 1e-9:
            continue
        best_k, best_ratio = -1, float("inf")
        for k in range(prev_k + 1, n):
            before, after = prefix[k] - prefix[prev_k], total_local - prefix[k]
            if before <= 0 or after <= 0:
                continue
            ratio = ((t - prev_t) / before) / ((target - t) / after)
            ratio = max(ratio, 1 / ratio)
            if ratio < best_ratio:
                best_k, best_ratio = k, ratio
        if best_k < 0 or best_ratio > MAX_ZONE_RATIO:
            continue
        cuts.append((best_k, t))
    cuts.append((n, target))
    if len(cuts) == 2:
        return [uniform] * n
    scales = [uniform] * n
    for (ka, ta), (kb, tb) in zip(cuts, cuts[1:]):
        zone_local = sum(local[ka:kb])
        if zone_local <= 0:
            return [uniform] * n
        for i in range(ka, kb):
            scales[i] = (tb - ta) / zone_local
    return scales


def allocate(
    named: list[tuple[str, int]],
    usage: Usage | None,
    unresolved: bool = False,
    calibrate: bool = False,
) -> tuple[list[Segment], bool]:
    """Split a call's billed input over its segments (in prompt order). Returns (segments, estimated).

    ``named`` holds (key, local token count) pairs in prompt order, framing included as ``overhead`` entries.
    ``calibrate`` enables cache-zone calibration (see :func:`zone_scales`); use it for APIs whose cache boundaries
    fall on block boundaries (Anthropic). OpenAI caches in fixed-size increments, so it gets one uniform scale.
    """
    local = [float(n) for _, n in named]
    local_total = sum(local)
    estimated = usage is None
    total = float(usage.total_input) if usage is not None else local_total
    read = float(usage.cache_read) if usage is not None else 0.0
    write = float(usage.cache_write) if usage is not None else 0.0

    remainder = 0.0
    if not local_total:
        scales: list[float] = []
        remainder = total
    elif unresolved:
        # Carried context we cannot see (an unknown previous_response_id): keep local counts, the gap is "mutated".
        scale = min(1.0, total / local_total)
        scales = [scale] * len(named)
        remainder = max(0.0, total - local_total * scale)
    elif calibrate:
        scales = zone_scales(local, total, read, write)
    else:
        scales = [total / local_total] * len(named)

    segs: list[Segment] = [Segment(key, n * s) for (key, _), n, s in zip(named, local, scales)]
    if remainder:
        segs.append(Segment("mutated" if local_total else "overhead", remainder))
    left_read, left_write = read, write
    for seg in segs:
        r = min(seg.tokens, max(0.0, left_read))
        left_read -= r
        w = min(seg.tokens - r, max(0.0, left_write))
        left_write -= w
        seg.cache_read, seg.cache_write = r, w

    merged: dict[str, Segment] = {}
    for s in segs:
        if s.key in merged:
            m = merged[s.key]
            m.tokens += s.tokens
            m.cache_read += s.cache_read
            m.cache_write += s.cache_write
        else:
            merged[s.key] = s
    return [s for s in merged.values() if s.tokens > 0], estimated


class RunSegmenter:
    """Assigns segment keys to every call of one run. Calls must be fed in call order."""

    def __init__(self, counter: TokenCounter):
        self.counter = counter
        self.produced: dict[str, int] = {}  # assistant canon digest -> producing call ordinal
        self.tool_names: dict[str, str] = {}
        self.tool_seen: dict[str, tuple[str, str]] = {}  # ref -> (digest, key)
        self.tool_ordinal: dict[str, int] = {}
        self.distinct: dict[str, dict[str, str]] = {k: {} for k in ("tools", "system", "system_message", "user")}
        self.responses_by_id: dict[str, dict[str, Any]] = {}
        self._responses_ctx: dict[int, tuple[list[Block], bool]] = {}
        self.call_ordinal = 0

    # -- keys

    def _distinct_key(self, kind: str, digest: str) -> str:
        seen = self.distinct[kind]
        if digest not in seen:
            n = len(seen) + 1
            if kind == "tools":
                seen[digest] = "tool_schemas" if n == 1 else f"tool_schemas#{n}"
            elif kind == "system":
                seen[digest] = "system_prompt" if n == 1 else f"system_prompt#{n}"
            elif kind == "system_message":
                seen[digest] = f"system_message#{n}"
            else:
                seen[digest] = "user_input" if n == 1 else f"user_message#{n - 1}"
        return seen[digest]

    def key_for(self, block: Block, occurrence: int = 0) -> str:
        """``occurrence`` numbers repeats of identical content within one request (the same refinement prompt sent
        twice is two instances, not one instance of double size)."""
        if block.kind in self.distinct:
            return self._distinct_key(block.kind, f"{block.digest}#{occurrence}" if occurrence else block.digest)
        if block.kind == "assistant":
            for call_id, name in block.tool_calls:
                if call_id and name:
                    self.tool_names.setdefault(call_id, name)
            ordinal = self.produced.get(block.digest)
            return f"assistant_turn#{ordinal}" if ordinal is not None else "mutated"
        # tool_result
        ident = block.ref or f"hash:{block.digest}"
        if ident in self.tool_seen:
            digest, key = self.tool_seen[ident]
            return key if digest == block.digest else "mutated"
        name = block.name or (self.tool_names.get(block.ref) if block.ref else None) or "unknown"
        self.tool_ordinal[name] = self.tool_ordinal.get(name, 0) + 1
        key = f"tool_result:{name}#{self.tool_ordinal[name]}"
        self.tool_seen[ident] = (block.digest, key)
        return key

    # -- per API

    def _responses_context(self, rec: dict[str, Any]) -> tuple[list[Block], bool]:
        """Conversation carried into a Responses call: the previous_response_id chain plus this call's input."""
        seq = rec["seq"]
        if seq in self._responses_ctx:
            return self._responses_ctx[seq]
        req = rec.get("request") or {}
        blocks: list[Block] = []
        unresolved = False
        prev_id = req.get("previous_response_id")
        if prev_id or req.get("conversation"):
            prev = self.responses_by_id.get(prev_id) if prev_id else None
            if prev is None:
                unresolved = True
            else:
                prev_blocks, prev_unresolved = self._responses_context(prev)
                blocks.extend(prev_blocks)
                blocks.extend(responses_output_blocks(prev.get("response") or {}))
                unresolved = prev_unresolved
        blocks.extend(responses_input_blocks(req))
        self._responses_ctx[seq] = (blocks, unresolved)
        return blocks, unresolved

    def request_blocks(self, rec: dict[str, Any]) -> tuple[list[Block], bool]:
        api, req = rec["api"], rec.get("request") or {}
        if api == "anthropic.messages":
            return anthropic_request_blocks(req), False
        if api == "openai.chat":
            return openai_chat_request_blocks(req), False
        blocks: list[Block] = []
        if req.get("tools"):
            blocks.append(Block("tools", _jdump(req["tools"]), _jdump(req["tools"])))
        if req.get("instructions"):
            blocks.append(Block("system", req["instructions"], req["instructions"]))
        ctx, unresolved = self._responses_context(rec)
        return blocks + ctx, unresolved

    @staticmethod
    def response_blocks(rec: dict[str, Any]) -> list[Block]:
        resp = rec.get("response") or {}
        if rec["api"] == "anthropic.messages":
            return anthropic_response_blocks(resp)
        if rec["api"] == "openai.chat":
            return openai_chat_response_blocks(resp)
        return responses_output_blocks(resp)

    def segment_call(self, rec: dict[str, Any]) -> dict[str, Any]:
        model = rec.get("model") or rec.get("response_model") or "unknown"
        usage = Usage.from_dict(rec["usage"]) if rec.get("usage") else None
        out: dict[str, Any] = {
            "seq": rec["seq"],
            "api": rec["api"],
            "model": model,
            "status": rec.get("status"),
            "streamed": rec.get("streamed", False),
            "latency_ms": rec.get("latency_ms"),
            "usage": usage.to_dict() if usage else None,
            "estimated": False,
            "segments": [],
        }
        if rec.get("status") is None or rec["status"] >= 400:
            out["error"] = _short_error(rec.get("error"))
            return out
        if rec.get("error"):
            out["error"] = _short_error(rec.get("error"))
        blocks, unresolved = self.request_blocks(rec)
        seen: dict[str, int] = {}
        named = []
        for b in blocks:
            occurrence = seen.get(b.digest, 0)
            seen[b.digest] = occurrence + 1
            named.append((self.key_for(b, occurrence), self.counter.count(b.text, model) + b.fixed_tokens))
        named = with_overhead(rec["api"], blocks, named)
        segs, estimated = allocate(named, usage, unresolved, calibrate=rec["api"] == "anthropic.messages")
        out["segments"] = [s.to_dict() for s in segs]
        out["estimated"] = estimated
        if unresolved:
            out["unresolved_context"] = True

        # Register this call's output so later calls can recognize it as carried context.
        self.call_ordinal += 1
        for b in self.response_blocks(rec):
            self.produced.setdefault(b.digest, self.call_ordinal)
            for call_id, name in b.tool_calls:
                if call_id and name:
                    self.tool_names.setdefault(call_id, name)
        if rec["api"] == "openai.responses":
            rid = (rec.get("response") or {}).get("id")
            if rid:
                self.responses_by_id[rid] = rec
        return out


def _short_error(err: Any) -> str | None:
    if err is None:
        return None
    s = err if isinstance(err, str) else json.dumps(err)
    return s[:500]


def segment_run(records: list[dict[str, Any]], counter: TokenCounter) -> list[dict[str, Any]]:
    seg = RunSegmenter(counter)
    return [seg.segment_call(r) for r in sorted(records, key=lambda r: r["seq"])]


def segment_texts(records: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Every (model, text) a run's segmentation will count; used to prefetch exact counts."""
    seg = RunSegmenter(TokenCounter(prefer="heuristic"))
    items: list[tuple[str, str]] = []
    for rec in sorted(records, key=lambda r: r["seq"]):
        if rec.get("status") is None or rec["status"] >= 400:
            continue
        blocks, _ = seg.request_blocks(rec)
        model = rec.get("model") or "unknown"
        items.extend((model, b.text) for b in blocks if b.text)
        seg.segment_call(rec)
    return items

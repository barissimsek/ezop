"""Local token counting used to split each call's billed input among its segments.

Counts only need to be *proportionally* right: every call's segment counts are scaled so they sum exactly to the
billed input. Methods, from least to most precise:

* ``heuristic``  - regex word/punctuation split. Used only when tiktoken is unavailable.
* ``approx``     - tiktoken ``o200k_base`` as a stand-in for Claude (Anthropic publishes no local tokenizer).
* ``openai``     - the model's own published tiktoken encoding (exact content counts for OpenAI models).
* ``anthropic-count-tokens`` - Anthropic's free ``/v1/messages/count_tokens`` endpoint (``token_counts: exact``).
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from collections import Counter as _Tally
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

log = logging.getLogger("ezop_agentcost.tokens")

_WORD = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def heuristic_count(text: str) -> int:
    n = 0
    for m in _WORD.finditer(text):
        tok = m.group(0)
        n += max(1, math.ceil(len(tok) / 4)) if tok[0].isalnum() or tok[0] == "_" else 1
    return n


class TokenCounter:
    """Counts tokens per (model, text) with memoization. Thread-safe."""

    def __init__(self, prefer: str = "auto"):
        self._cache: dict[tuple[str, str], int] = {}
        self._exact: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()
        self._encodings: dict[str, Any] = {}
        self.methods: _Tally[str] = _Tally()
        self._tiktoken: Any = None
        if prefer != "heuristic":
            try:
                import tiktoken

                tiktoken.get_encoding("o200k_base")
                self._tiktoken = tiktoken
            except Exception as e:  # missing wheel or no network to fetch the encoding
                log.warning("tiktoken unavailable (%s); falling back to heuristic token counts", e)

    def _encoding_for(self, model: str) -> tuple[Any, str]:
        if self._tiktoken is None:
            return None, "heuristic"
        is_openai = not model.lower().startswith("claude") and "claude" not in model.lower()
        key = model if is_openai else "_approx"
        if key not in self._encodings:
            enc = None
            if is_openai:
                try:
                    enc = self._tiktoken.encoding_for_model(model)
                except KeyError:
                    enc = None
            self._encodings[key] = enc or self._tiktoken.get_encoding("o200k_base")
        return self._encodings[key], "openai" if is_openai else "approx"

    def method_for(self, model: str) -> str:
        return self._encoding_for(model)[1]

    def set_exact(self, model: str, text: str, tokens: int) -> None:
        with self._lock:
            self._exact[(model, text)] = tokens

    def count(self, text: str, model: str) -> int:
        if not text:
            return 0
        key = (model, text)
        with self._lock:
            if key in self._exact:
                self.methods["anthropic-count-tokens"] += 1
                return self._exact[key]
            if key in self._cache:
                return self._cache[key]
        enc, method = self._encoding_for(model)
        n = len(enc.encode(text, disallowed_special=())) if enc is not None else heuristic_count(text)
        with self._lock:
            self._cache[key] = n
            self.methods[method] += 1
        return n

    def describe(self) -> str:
        if not self.methods:
            return "none"
        return ", ".join(f"{m} ({n} segments)" for m, n in self.methods.most_common())


def prefetch_anthropic_exact(
    counter: TokenCounter,
    items: list[tuple[str, str]],
    api_key: str,
    base_url: str = "https://api.anthropic.com",
    max_requests: int = 500,
    concurrency: int = 4,
    client: httpx.Client | None = None,
) -> int:
    """Count each unique (model, text) with ``/v1/messages/count_tokens``.

    Each text is counted as a one-message prompt minus a one-character baseline prompt, which removes the message
    framing and leaves the content's own tokens. Texts are deduplicated, the largest are counted first, and anything
    past ``max_requests`` keeps its approximate count. Returns the number of texts counted exactly.
    """
    unique = sorted(set(items), key=lambda mt: -len(mt[1]))
    baselines: dict[str, int] = {}
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    budget = max(0, max_requests - len({m for m, _ in unique}))

    def count_one(model: str, text: str) -> int | None:
        for attempt in range(4):
            r = http.post(
                f"{base_url.rstrip('/')}/v1/messages/count_tokens",
                headers=headers,
                json={"model": model, "messages": [{"role": "user", "content": text}]},
            )
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(float(r.headers.get("retry-after", 2**attempt)))
                continue
            if r.status_code >= 400:
                log.warning("count_tokens failed for %s: %s %s", model, r.status_code, r.text[:200])
                return None
            return int(r.json()["input_tokens"])
        return None

    try:
        for model in {m for m, _ in unique}:
            base = count_one(model, ".")
            if base is not None:
                baselines[model] = base
        todo = [(m, t) for m, t in unique if m in baselines][:budget]
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(lambda mt: (mt, count_one(*mt)), todo))
        done = 0
        for (model, text), n in results:
            if n is not None:
                counter.set_exact(model, text, max(0, n - baselines[model] + 1))
                done += 1
        if len(unique) > len(todo):
            log.info("exact token counts for %d of %d segment texts; the rest stay approximate", done, len(unique))
        return done
    finally:
        if own_client:
            http.close()

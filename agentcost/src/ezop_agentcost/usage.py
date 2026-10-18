"""Provider-neutral billed usage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Usage:
    """Billed tokens for one LLM call.

    ``input`` is the *uncached* part of the prompt. The full prompt size is ``total_input``.
    """

    input: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    output: int = 0

    @property
    def cache_write(self) -> int:
        return self.cache_write_5m + self.cache_write_1h

    @property
    def total_input(self) -> int:
        return self.input + self.cache_read + self.cache_write

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Usage:
        return cls(
            **{k: int(d.get(k) or 0) for k in ("input", "cache_read", "cache_write_5m", "cache_write_1h", "output")}
        )

    @classmethod
    def from_anthropic(cls, u: dict[str, Any]) -> Usage:
        """Messages API ``usage``: ``input_tokens`` excludes cache reads and writes."""
        write = int(u.get("cache_creation_input_tokens") or 0)
        breakdown = u.get("cache_creation") or {}
        w1h = int(breakdown.get("ephemeral_1h_input_tokens") or 0)
        w5m = int(breakdown.get("ephemeral_5m_input_tokens") or 0)
        if w1h + w5m != write:
            w5m, w1h = write - w1h, w1h
        return cls(
            input=int(u.get("input_tokens") or 0),
            cache_read=int(u.get("cache_read_input_tokens") or 0),
            cache_write_5m=w5m,
            cache_write_1h=w1h,
            output=int(u.get("output_tokens") or 0),
        )

    @classmethod
    def from_openai_chat(cls, u: dict[str, Any]) -> Usage:
        """Chat Completions ``usage``: ``prompt_tokens`` includes ``cached_tokens``."""
        prompt = int(u.get("prompt_tokens") or 0)
        cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        return cls(input=prompt - cached, cache_read=cached, output=int(u.get("completion_tokens") or 0))

    @classmethod
    def from_openai_responses(cls, u: dict[str, Any]) -> Usage:
        """Responses API ``usage``: ``input_tokens`` includes ``cached_tokens``."""
        prompt = int(u.get("input_tokens") or 0)
        cached = int((u.get("input_tokens_details") or {}).get("cached_tokens") or 0)
        return cls(input=prompt - cached, cache_read=cached, output=int(u.get("output_tokens") or 0))

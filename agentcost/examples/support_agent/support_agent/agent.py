"""The agent loop: tool use until the model answers, then a refinement pass.

``SUPPORT_AGENT_VARIANT`` (comma-separated) switches on the seeded regressions used by the agentcost benchmark,
so each one can be exercised without a branch per change:

==================  ===================================================================
full_line_items     lookup_order returns every line item with all fields (~4x larger)
longer_prompt       the system prompt grows by a ~600-token brand voice guide
timestamp_top       the current time moves to the top of the cached system prompt
extra_refine        one extra refinement iteration
pricier_model       the model switches to a pricier tier
noop                no behavior change (stands in for a refactor)
==================  ===================================================================
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import anthropic

from support_agent.prompts import BRAND_VOICE, POLICY, REFINE_PROMPT
from support_agent.tools import TOOLS, run_tool

MAX_TOOL_STEPS = 8


def variants() -> set[str]:
    return {v.strip() for v in os.environ.get("SUPPORT_AGENT_VARIANT", "").split(",") if v.strip()}


def model() -> str:
    if "pricier_model" in variants():
        return os.environ.get("SUPPORT_AGENT_PRICIER_MODEL", "claude-fable-5-1")
    return os.environ.get("SUPPORT_AGENT_MODEL", "claude-opus-5-5")


def system_blocks() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    policy = POLICY + (BRAND_VOICE if "longer_prompt" in variants() else "")
    if "timestamp_top" in variants():
        # Seeded regression #3: dynamic content before the static prefix breaks the prompt cache on every call.
        return [{"type": "text", "text": f"Current time: {now}\n\n{policy}", "cache_control": {"type": "ephemeral"}}]
    return [
        {"type": "text", "text": policy, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"Current time: {now}"},
    ]


def call(client: anthropic.Anthropic, messages: list[dict[str, Any]]) -> anthropic.types.Message:
    with client.messages.stream(
        model=model(),
        max_tokens=4096,
        system=system_blocks(),
        tools=TOOLS,
        messages=messages,
        output_config={"effort": "low"},
    ) as stream:
        return stream.get_final_message()


def text_of(message: anthropic.types.Message) -> str:
    return "".join(b.text for b in message.content if b.type == "text").strip()


def run(task: dict[str, Any]) -> dict[str, Any]:
    client = anthropic.Anthropic()  # honors ANTHROPIC_BASE_URL, which agentcost points at its proxy
    messages: list[dict[str, Any]] = [{"role": "user", "content": task["message"]}]
    steps = 0
    tools_used: list[str] = []
    response = None
    for _ in range(MAX_TOOL_STEPS):
        response = call(client, messages)
        steps += 1
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            break
        results = []
        for block in response.content:
            if block.type == "tool_use":
                tools_used.append(block.name)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(run_tool(block.name, block.input)),
                    }
                )
        messages.append({"role": "user", "content": results})
    answer = text_of(response) if response else ""

    for _ in range(2 if "extra_refine" in variants() else 1):
        messages.append({"role": "user", "content": REFINE_PROMPT})
        response = call(client, messages)
        steps += 1
        messages.append({"role": "assistant", "content": response.content})
        answer = text_of(response) or answer

    return {"answer": answer, "steps": steps, "tools": tools_used}

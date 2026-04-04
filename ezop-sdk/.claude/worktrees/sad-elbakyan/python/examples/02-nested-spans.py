"""
Nested spans example.

Demonstrates hierarchical spans and events emitted inside spans.

    model.prompt
    ├── emit: llm.request
    ├── tool.call
    │   ├── emit: tool_call_started
    │   └── emit: tool_call_completed
    └── emit: llm.response

Setup:
    pip install ezop
    export EZOP_API_KEY=your-key

Run:
    python examples/02-nested-spans.py
"""

from ezop import Agent

agent = Agent.init(
    name="my-agent",
    owner="my-team",
    version="v1.0",
    runtime="python",
)

try:
    with agent.span("model.prompt", metadata={"model": "claude-sonnet-4-6"}):

        agent.emit(
            name="llm.request",
            category="llm",
            type="llm_request",
            input={"prompt": "What is the weather in Paris?"},
            metadata={"usage": {"input_tokens": 12, "output_tokens": 0}},
        )

        # Child span — parent_id is set automatically
        with agent.span("tool.call", metadata={"tool": "weather_api"}):

            agent.emit(
                name="tool_call_started",
                category="tool",
                type="tool_call_started",
                subtype="http",
                input={"city": "Paris"},
            )

            # replace with real tool call
            weather = {"temperature": "18°C", "condition": "sunny"}

            agent.emit(
                name="tool_call_completed",
                category="tool",
                type="tool_call_completed",
                subtype="http",
                output=weather,
            )

        agent.emit(
            name="llm.response",
            category="llm",
            type="llm_response",
            output={"text": f"It is {weather['temperature']} and {weather['condition']} in Paris."},
            metadata={"usage": {"input_tokens": 12, "output_tokens": 18}},
        )

    agent.close(status="success")

except Exception as e:
    agent.close(status="failed", message=str(e))
    raise

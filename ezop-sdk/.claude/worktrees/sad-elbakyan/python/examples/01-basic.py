"""
Basic Ezop SDK example.

Setup:
    pip install ezop
    export EZOP_API_KEY=your-key

Run:
    python examples/basic.py
"""

from ezop import Agent

agent = Agent.init(
    name="my-agent",
    owner="my-team",
    version="v1.0",
    runtime="python",
)

try:
    with agent.span("llm.call", metadata={"model": "claude-sonnet-4-6"}):
        # replace with real LLM call
        response = "Hello, world!"

        agent.emit(
            name="llm.response",
            category="llm",
            type="llm_response",
            output={"text": response},
            metadata={
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                }
            },
        )

    agent.close(status="success")

except Exception as e:
    agent.close(status="failed", message=str(e))
    raise

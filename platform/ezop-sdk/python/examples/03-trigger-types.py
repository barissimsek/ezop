"""
Trigger types example.

Demonstrates how to record what triggered a run using trigger_type and trigger_id.

Setup:
    pip install ezop
    export EZOP_API_KEY=your-key

Run:
    python examples/03-trigger-types.py
"""

import os

from ezop import Agent

# ── API-triggered run ─────────────────────────────────────────────────────────
# A run started by an incoming API request.

api_agent = Agent.init(
    name="api-agent",
    owner="my-team",
    version="v1.0",
    runtime="python",
    trigger_type="api",
    trigger_id="/api/v1/summarize",
)
api_agent.close(status="success")


# ── Cron-triggered run ────────────────────────────────────────────────────────
# A run started by a scheduled job.

cron_agent = Agent.init(
    name="digest-agent",
    owner="my-team",
    version="v1.0",
    runtime="python",
    trigger_type="cron",
    trigger_id="nightly-digest",
)
cron_agent.close(status="success")


# ── Webhook-triggered run ─────────────────────────────────────────────────────
# A run started by an incoming webhook (e.g. from GitHub or Stripe).

webhook_agent = Agent.init(
    name="webhook-agent",
    owner="my-team",
    version="v1.0",
    runtime="python",
    trigger_type="webhook",
    trigger_id="github",
)
webhook_agent.close(status="success")


# ── User-triggered run ────────────────────────────────────────────────────────
# A run started by a specific user action.

user_id = os.environ.get("USER_ID", "user-123")

user_agent = Agent.init(
    name="chat-agent",
    owner="my-team",
    version="v1.0",
    runtime="python",
    trigger_type="user",
    trigger_id=user_id,
)
user_agent.close(status="success")


# ── Agent-triggered run (parent → child) ──────────────────────────────────────
# An orchestrator agent spawns a child agent and passes its run context.
# The child records trigger_type="agent" and parent_run_id from the parent context.

orchestrator = Agent.init(
    name="orchestrator",
    owner="my-team",
    version="v1.0",
    runtime="python",
    trigger_type="api",
    trigger_id="/api/v1/pipeline",
)

ctx = orchestrator.get_context()

child = Agent.init(
    name="researcher",
    owner="my-team",
    version="v1.0",
    runtime="python",
    trigger_type="agent",
    trigger_id=ctx.run_id,   # the parent's run ID
    parent_run_id=ctx.run_id,
)

child.close(status="success")
orchestrator.close(status="success")

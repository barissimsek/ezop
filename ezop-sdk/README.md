# Ezop SDK

Official opensource client libraries for the [Ezop](https://ezop.ai) platform.

## What is Ezop?

As AI agents take on real work inside companies, a critical question emerges: **what are they actually doing?**

Think Datadog for AI agents — a platform that gives you complete visibility into every agent running in your organization:

- **Identity** — which agents exist, who owns them, what versions are deployed
- **Permissions** — what each agent is allowed to do, enforced and auditable
- **Observability** — every run, every decision, every outcome in one place
- **Safety** — detect agents behaving outside their expected boundaries

### Agent action auditing

Every agent action is logged with full context — Stripe-style audit trails for AI decisions:

| Field | Description |
|---|---|
| Who initiated | The user or system that triggered the run |
| Which agent | Identity, owner, and version |
| What prompt | The input the agent received |
| What tools used | Every tool call made during the run |
| What outcome | Final status, tokens, cost, and metadata |

This solves compliance and legal risk. Enterprises need to prove their AI automation is behaving safely and within policy — Ezop gives them the receipts.

## Available SDKs

| Language | Package | Documentation |
|---|---|---|
| Python | `pip install ezop` | [python/](python/) |
| Node.js | coming soon | — |
| Go | coming soon | — |

## Quick example

```python
from ezop import Agent

agent = Agent.init(
    name="support-bot",
    owner="growth-team",
    version="v1.0",
    runtime="langchain",
)

... your agent logic ...

agent.close(status="success", total_tokens=350, total_cost=0.007)
```

See the [Python SDK README](python/README.md) for the full reference.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

## License

[Apache 2.0](LICENSE)

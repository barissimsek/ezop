"""agentcost entrypoint: run the agent on one fixture.

agentcost starts this script once per fixture sample. Contract:
  * read the fixture input (JSON) from --input
  * write the agent's final answer to --output (JSON or text)
  * build provider clients the default way, so they pick up ANTHROPIC_BASE_URL / OPENAI_BASE_URL,
    which agentcost points at its recording proxy

Exit non-zero on failure; agentcost reports crashed runs separately so a broken agent never looks cheap.
"""

import argparse
import json


def run_agent(task: dict) -> dict:
    # Replace with a call into your agent, e.g.:
    #   from my_agent import Agent
    #   return {"answer": Agent().run(task["message"])}
    raise NotImplementedError("edit agentcost_entry.py to call your agent")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.input) as f:
        task = json.load(f)
    result = run_agent(task)
    with open(args.output, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()

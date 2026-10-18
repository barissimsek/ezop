"""agentcost entrypoint: ``python -m support_agent.run --input {fixture} --output {output}``."""

from __future__ import annotations

import argparse
import json

from support_agent.agent import run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.input) as f:
        task = json.load(f)
    result = run(task)
    with open(args.output, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()

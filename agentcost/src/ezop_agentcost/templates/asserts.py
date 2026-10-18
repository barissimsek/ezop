"""Fixture assertions.

A fixture names one of these functions in its "assert" key. Each function receives the agent's final output
(parsed JSON if the output file is JSON, otherwise text) and, optionally, the fixture input. Return False or raise
AssertionError to fail; returning None or True passes.
"""


def _text(output):
    return output if isinstance(output, str) else str(output.get("answer", output))


def check_mentions_refund(output, fixture_input):
    assert "refund" in _text(output).lower(), "answer never mentions the refund"

"""Quality checks for the support agent fixtures."""

import re


def check_answer(output, fixture_input):
    answer = output["answer"] if isinstance(output, dict) else str(output)
    order_id = re.search(r"\b(1\d{3})\b", fixture_input["message"]).group(1)
    assert answer, "empty answer"
    assert order_id in answer, f"answer does not mention order {order_id}"
    assert "lookup_order" in output.get("tools", []), "agent answered without looking up the order"

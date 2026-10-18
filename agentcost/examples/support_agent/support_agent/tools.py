"""Tools backed by seeded JSON data, so tool results are stable between base and head runs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> Any:
    return json.loads((DATA / name).read_text())


def _variants() -> set[str]:
    return {v.strip() for v in os.environ.get("SUPPORT_AGENT_VARIANT", "").split(",") if v.strip()}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "lookup_order",
        "description": "Look up an order by its numeric id. Returns status, dates, totals and items.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "Numeric order id, e.g. 1042"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "lookup_customer",
        "description": "Look up a customer profile by email: name, tier, tenure and open tickets.",
        "input_schema": {
            "type": "object",
            "properties": {"email": {"type": "string"}},
            "required": ["email"],
        },
    },
    {
        "name": "search_kb",
        "description": "Search the support knowledge base. Returns the best matching articles.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "check_refund_policy",
        "description": "Decide whether an order is eligible for a refund for the given reason.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["order_id", "reason"],
        },
    },
    {
        "name": "create_ticket",
        "description": "Open a ticket for a human specialist (warranty, fraud, or anything you cannot resolve).",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}, "summary": {"type": "string"}},
            "required": ["order_id", "summary"],
        },
    },
]


def lookup_order(order_id: str) -> dict[str, Any]:
    order = _load("orders.json").get(str(order_id))
    if order is None:
        return {"error": f"order {order_id} not found"}
    if "full_line_items" in _variants():
        # Seeded regression #1: return every line item with all of its fields.
        return order
    summary = {k: v for k, v in order.items() if k != "line_items"}
    summary["items"] = [{"name": li["name"], "qty": li["qty"]} for li in order["line_items"]]
    return summary


def lookup_customer(email: str) -> dict[str, Any]:
    return _load("customers.json").get(email) or {"error": f"no customer with email {email}"}


def search_kb(query: str) -> list[dict[str, Any]]:
    words = {w.strip(".,?!").lower() for w in query.split() if len(w) > 3}
    scored = []
    for art in _load("kb.json"):
        text = (art["title"] + " " + art["body"]).lower()
        scored.append((sum(1 for w in words if w in text), art))
    scored.sort(key=lambda x: -x[0])
    return [a for s, a in scored[:2] if s > 0] or [scored[0][1]]


def check_refund_policy(order_id: str, reason: str) -> dict[str, Any]:
    order = _load("orders.json").get(str(order_id))
    if order is None:
        return {"eligible": False, "why": "unknown order"}
    if order["status"] == "in_transit":
        return {"eligible": False, "why": "order is still in transit; refunds open once it is delivered or lost"}
    warranty = any(w in reason.lower() for w in ("warranty", "stopped", "broke", "failed"))
    return {
        "eligible": True,
        "why": "within the 30-day window" if not warranty else "covered by the one-year warranty",
        "requires_ticket": warranty,
    }


def create_ticket(order_id: str, summary: str) -> dict[str, Any]:
    return {"ticket_id": f"T-{order_id}-1", "queue": "warranty", "summary": summary}


def run_tool(name: str, args: dict[str, Any]) -> Any:
    fn = {
        "lookup_order": lookup_order,
        "lookup_customer": lookup_customer,
        "search_kb": search_kb,
        "check_refund_policy": check_refund_policy,
        "create_ticket": create_ticket,
    }.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**args)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}

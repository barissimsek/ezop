"""
Plan limit enforcement.

Limits are defined in plans.limits (jsonb):
  {
    "agents":           <int>   # max registered agents per org
    "events_per_month": <int>   # max events emitted per calendar month
    "retention_days":   <int>   # data retention (not enforced at request time)
  }

A missing, null, or -1 limit value means unlimited.
"""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _fetch_plan_limits(db: Session, org_id: str) -> dict:
    """Return the limits dict for the org's current plan (latest version)."""
    org = (
        db.execute(
            text("SELECT plan FROM organizations WHERE id = :org_id"),
            {"org_id": org_id},
        )
        .mappings()
        .first()
    )

    if org is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization not found.")

    plan = (
        db.execute(
            text("""
            SELECT limits FROM plans
            WHERE name = :plan_name
            ORDER BY version DESC
            LIMIT 1
        """),
            {"plan_name": org["plan"]},
        )
        .mappings()
        .first()
    )

    if plan is None:
        logger.warning("No plan record found for plan=%s org_id=%s", org["plan"], org_id)
        return {}

    return plan["limits"] or {}


# ── Public assertion functions ────────────────────────────────────────────────


def assert_agents_limit(db: Session, org_id: str, name: str, owner: str) -> None:
    """
    Block registration if the org is at its agent limit.
    Upserts on an existing (name, owner, org_id) are always allowed.
    """
    limits = _fetch_plan_limits(db, org_id)
    max_agents = limits.get("agents")
    if max_agents is None or max_agents == -1:
        return  # unlimited

    existing = db.execute(
        text("""
            SELECT id FROM agents
            WHERE organization_id = :org_id AND name = :name AND owner = :owner
        """),
        {"org_id": org_id, "name": name, "owner": owner},
    ).first()
    if existing:
        return  # updating an existing agent, always allowed

    current = db.execute(
        text("SELECT COUNT(*) FROM agents WHERE organization_id = :org_id"),
        {"org_id": org_id},
    ).scalar()

    if current >= max_agents:
        logger.warning(
            "Agent limit reached org_id=%s current=%d limit=%d", org_id, current, max_agents
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Agent limit reached ({current}/{max_agents}). Upgrade your plan to register more agents.",
        )


def assert_events_limit(db: Session, org_id: str) -> None:
    """Block event emission if the org has exceeded its monthly event quota."""
    limits = _fetch_plan_limits(db, org_id)
    max_events = limits.get("events_per_month")
    if max_events is None or max_events == -1:
        return  # unlimited

    start_of_month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    current = db.execute(
        text("""
            SELECT COUNT(*) FROM events
            WHERE organization_id = :org_id AND created_at >= :start
        """),
        {"org_id": org_id, "start": start_of_month},
    ).scalar()

    if current >= max_events:
        logger.warning(
            "Event limit reached org_id=%s current=%d limit=%d", org_id, current, max_events
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Monthly event limit reached ({current}/{max_events}). Upgrade your plan to emit more events.",
        )

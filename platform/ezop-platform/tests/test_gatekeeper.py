"""Tests for plan limit enforcement in gatekeeper."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.gatekeeper import assert_agents_limit, assert_events_limit


def make_db(org_row, plan_row, agent_count=0):
    db = MagicMock()

    def execute_side_effect(query, params=None):
        result = MagicMock()
        sql = str(query)
        if "organizations" in sql:
            result.mappings.return_value.first.return_value = org_row
        elif "plans" in sql:
            result.mappings.return_value.first.return_value = plan_row
        elif "COUNT" in sql:
            result.scalar.return_value = agent_count
        elif "SELECT id FROM agents" in sql:
            result.first.return_value = None  # not an existing agent
        else:
            result.first.return_value = None
            result.mappings.return_value.first.return_value = None
        return result

    db.execute.side_effect = execute_side_effect
    return db


class TestAgentsLimit:
    def test_minus_one_means_unlimited(self):
        db = make_db(
            org_row={"plan": "free"},
            plan_row={"limits": {"agents": -1}},
            agent_count=9999,
        )
        # Should not raise
        assert_agents_limit(db, "org-1", "agent", "owner")

    def test_none_limit_means_unlimited(self):
        db = make_db(
            org_row={"plan": "free"},
            plan_row={"limits": {}},
            agent_count=9999,
        )
        assert_agents_limit(db, "org-1", "agent", "owner")

    def test_at_limit_raises_429(self):
        db = make_db(
            org_row={"plan": "free"},
            plan_row={"limits": {"agents": 5}},
            agent_count=5,
        )
        with pytest.raises(HTTPException) as exc_info:
            assert_agents_limit(db, "org-1", "new-agent", "owner")
        assert exc_info.value.status_code == 429

    def test_under_limit_passes(self):
        db = make_db(
            org_row={"plan": "free"},
            plan_row={"limits": {"agents": 5}},
            agent_count=4,
        )
        assert_agents_limit(db, "org-1", "new-agent", "owner")

    def test_org_not_found_raises_403(self):
        db = make_db(org_row=None, plan_row=None)
        with pytest.raises(HTTPException) as exc_info:
            assert_agents_limit(db, "bad-org", "agent", "owner")
        assert exc_info.value.status_code == 403


class TestEventsLimit:
    def test_minus_one_means_unlimited(self):
        db = MagicMock()
        db.execute.return_value.mappings.return_value.first.side_effect = [
            {"plan": "free"},
            {"limits": {"events_per_month": -1}},
        ]
        assert_events_limit(db, "org-1")

    def test_none_limit_means_unlimited(self):
        db = MagicMock()
        org = {"plan": "free"}
        plan = {"limits": {}}
        db.execute.return_value.mappings.return_value.first.side_effect = [org, plan]
        assert_events_limit(db, "org-1")

    def test_at_limit_raises_429(self):
        db = MagicMock()

        call_count = 0

        def side_effect(query, params=None):
            nonlocal call_count
            result = MagicMock()
            sql = str(query)
            if "organizations" in sql:
                result.mappings.return_value.first.return_value = {"plan": "free"}
            elif "plans" in sql:
                result.mappings.return_value.first.return_value = {
                    "limits": {"events_per_month": 100}
                }
            elif "COUNT" in sql:
                result.scalar.return_value = 100
            return result

        db.execute.side_effect = side_effect
        with pytest.raises(HTTPException) as exc_info:
            assert_events_limit(db, "org-1")
        assert exc_info.value.status_code == 429

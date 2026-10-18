"""Tests for /spans endpoints."""

from tests.conftest import AGENT_ID, ORG_ID, RUN_ID, SPAN_ID, make_exec

SPAN_ROW = {
    "id": SPAN_ID,
    "run_id": RUN_ID,
    "agent_id": AGENT_ID,
    "name": "llm.call",
    "organization_id": ORG_ID,
    "start_time": "2024-01-01T00:00:00+00:00",
    "end_time": "2024-01-01T00:00:01+00:00",
    "parent_id": None,
    "metadata": None,
    "created_at": "2024-01-01T00:00:00+00:00",
    "updated_at": "2024-01-01T00:00:00+00:00",
}


class TestCloseSpan:
    def test_returns_200(self, client, db):
        db.execute.return_value = make_exec(mapping=SPAN_ROW)
        resp = client.patch(
            f"/spans/{SPAN_ID}",
            json={"end_time": "2024-01-01T00:00:01+00:00"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == SPAN_ID

    def test_response_envelope(self, client, db):
        db.execute.return_value = make_exec(mapping=SPAN_ROW)
        resp = client.patch(
            f"/spans/{SPAN_ID}",
            json={"end_time": "2024-01-01T00:00:01+00:00"},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["error"] is None

    def test_span_not_found_returns_404(self, client, db):
        db.execute.return_value = make_exec(mapping=None)
        resp = client.patch(
            f"/spans/{SPAN_ID}",
            json={"end_time": "2024-01-01T00:00:01+00:00"},
        )
        assert resp.status_code == 404

    def test_missing_end_time_returns_422(self, client, db):
        resp = client.patch(f"/spans/{SPAN_ID}", json={})
        assert resp.status_code == 422

    def test_requires_auth(self, unauthed_client):
        resp = unauthed_client.patch(
            f"/spans/{SPAN_ID}",
            json={"end_time": "2024-01-01T00:00:01+00:00"},
        )
        assert resp.status_code == 401

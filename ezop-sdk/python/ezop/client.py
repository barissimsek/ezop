import logging
from typing import Optional

import requests

from .config import Config

logger = logging.getLogger(__name__)


class EzopClient:
    def _headers(self):
        return {
            "Authorization": f"Bearer {Config.EZOP_API_KEY}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, body: dict) -> dict:
        url = f"{Config.EZOP_API_URL}{path}"
        logger.debug("POST %s body=%s", url, body)
        response = requests.post(url, json=body, headers=self._headers())
        if response.status_code not in (200, 201):
            logger.error("POST %s failed status=%s body=%s", url, response.status_code, response.text)
            raise Exception(f"Ezop API error: {response.text}")
        logger.debug("POST %s status=%s", url, response.status_code)
        return response.json()

    def _patch(self, path: str, body: dict) -> dict:
        url = f"{Config.EZOP_API_URL}{path}"
        logger.debug("PATCH %s body=%s", url, body)
        response = requests.patch(url, json=body, headers=self._headers())
        if response.status_code != 200:
            logger.error("PATCH %s failed status=%s body=%s", url, response.status_code, response.text)
            raise Exception(f"Ezop API error: {response.text}")
        logger.debug("PATCH %s status=%s", url, response.status_code)
        return response.json()

    def register_agent(self, agent_data: dict) -> dict:
        logger.info("Registering agent name=%s owner=%s", agent_data.get("name"), agent_data.get("owner"))
        result = self._post("/agents/register", agent_data)
        logger.info("Agent registered id=%s", result.get("data", {}).get("id"))
        return result

    def create_version(self, agent_id: str, version_data: dict) -> dict:
        logger.info("Creating version agent_id=%s version=%s", agent_id, version_data.get("version"))
        result = self._post(f"/agents/{agent_id}/versions", version_data)
        logger.info("Version created id=%s", result.get("data", {}).get("id"))
        return result

    def start_run(
        self,
        agent_id: str,
        version_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        parent_run_id: Optional[str] = None,
    ) -> dict:
        logger.info("Starting run agent_id=%s version_id=%s", agent_id, version_id)
        body: dict = {}
        if version_id is not None:
            body["version_id"] = version_id
        if user_id is not None:
            body["user_id"] = user_id
        if metadata is not None:
            body["metadata"] = metadata
        if parent_run_id is not None:
            body["parent_run_id"] = parent_run_id
        result = self._post(f"/agents/{agent_id}/runs", body)
        logger.info("Run started id=%s", result.get("data", {}).get("id"))
        return result

    def end_run(self, run_id: str, status: str, metadata: Optional[dict] = None, message: Optional[str] = None) -> dict:
        logger.info("Ending run id=%s status=%s", run_id, status)
        body: dict = {"status": status}
        if metadata is not None:
            body["metadata"] = metadata
        if message is not None:
            body["message"] = message
        result = self._patch(f"/runs/{run_id}", body)
        logger.info("Run ended id=%s status=%s", run_id, status)
        return result

    def create_span(self, run_id: str, span_data: dict) -> dict:
        logger.info("Creating span run_id=%s name=%s", run_id, span_data.get("name"))
        result = self._post(f"/runs/{run_id}/spans", span_data)
        logger.debug("Span created id=%s", span_data.get("id"))
        return result

    def end_span(self, span_id: str, data: dict) -> dict:
        logger.info("Ending span id=%s", span_id)
        result = self._patch(f"/spans/{span_id}", data)
        logger.debug("Span ended id=%s", span_id)
        return result

    def emit_event(self, run_id: str, event_data: dict) -> dict:
        logger.info("Emitting event run_id=%s name=%s", run_id, event_data.get("name"))
        result = self._post(f"/runs/{run_id}/events", event_data)
        logger.debug("Event emitted id=%s", result.get("data", {}).get("id"))
        return result

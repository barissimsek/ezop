"""Minimal GitHub REST client: baseline artifacts and the sticky PR comment."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

import httpx

from ezop_agentcost.render import MARKER


class GitHubError(RuntimeError):
    pass


class GitHub:
    def __init__(
        self, token: str, repo: str, api_url: str = "https://api.github.com", client: httpx.Client | None = None
    ):
        self.repo = repo
        self.api = api_url.rstrip("/")
        self.http = client or httpx.Client(timeout=30.0, follow_redirects=True)
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _req(self, method: str, path: str, **kw: Any) -> httpx.Response:
        url = path if path.startswith("http") else f"{self.api}{path}"
        r = self.http.request(method, url, headers=self.headers, **kw)
        if r.status_code >= 400:
            raise GitHubError(f"GitHub {method} {path} -> {r.status_code}: {r.text[:300]}")
        return r

    # -- baselines

    def find_artifact(self, name: str) -> dict[str, Any] | None:
        """Newest unexpired artifact with this exact name."""
        r = self._req("GET", f"/repos/{self.repo}/actions/artifacts", params={"name": name, "per_page": 20})
        arts = [a for a in r.json().get("artifacts", []) if a.get("name") == name and not a.get("expired")]
        arts.sort(key=lambda a: a.get("created_at") or "", reverse=True)
        return arts[0] if arts else None

    def download_report(self, artifact: dict[str, Any], filename: str = "report.json") -> dict[str, Any]:
        r = self._req("GET", artifact["archive_download_url"])
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            names = [n for n in z.namelist() if n.endswith(filename)]
            if not names:
                raise GitHubError(f"artifact {artifact.get('name')} has no {filename}")
            return json.loads(z.read(names[0]))

    @staticmethod
    def artifact_age_days(artifact: dict[str, Any], now: datetime | None = None) -> float:
        created = datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00"))
        return ((now or datetime.now(timezone.utc)) - created).total_seconds() / 86400

    # -- sticky comment

    def upsert_comment(self, pr_number: int, body: str) -> str:
        """Create the agentcost comment, or update it in place on later pushes. Returns the comment URL."""
        existing = None
        page = 1
        while existing is None:
            r = self._req(
                "GET", f"/repos/{self.repo}/issues/{pr_number}/comments", params={"per_page": 100, "page": page}
            )
            batch = r.json()
            existing = next((c for c in batch if MARKER in (c.get("body") or "")), None)
            if len(batch) < 100:
                break
            page += 1
        if existing:
            r = self._req("PATCH", f"/repos/{self.repo}/issues/comments/{existing['id']}", json={"body": body})
        else:
            r = self._req("POST", f"/repos/{self.repo}/issues/{pr_number}/comments", json={"body": body})
        return r.json().get("html_url", "")

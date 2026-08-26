"""Small dependency-free client for Graphtyn's stable memory API."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


class GraphtynClient:
    def __init__(self, base_url: str = "http://127.0.0.1:9210", token: str | None = None,
                 timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.token, self.timeout = token, timeout

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.base_url + path,
            data=json.dumps(payload).encode() if payload is not None else None, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode())

    def ingest_turn(self, **payload: Any) -> dict[str, Any]:
        return self._request("POST", "/api/v1/memory/ingest", payload)

    def context(self, **payload: Any) -> dict[str, Any]:
        return self._request("POST", "/api/v1/context", payload)

    def discover_imports(self, **payload: Any) -> dict[str, Any]:
        return self._request("POST", "/api/v1/imports/discover", payload)

    def start_import(self, **payload: Any) -> dict[str, Any]:
        return self._request("POST", "/api/v1/imports", payload)

    def import_status(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/imports/{urllib.parse.quote(job_id)}")

    def event(self, name: str, **payload: Any) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/events/{urllib.parse.quote(name)}", payload)

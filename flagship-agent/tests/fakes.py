"""In-memory fake of the mock booking API (same routes and status codes)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class FakeBookingApi:
    """Mimics the routes and status codes of ``mock-booking-api``."""

    reservations: dict[str, dict[str, Any]] = field(default_factory=dict)
    idempotency: dict[str, dict[str, Any]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)
    down: bool = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            return httpx.Response(503)
        parts = request.url.path.strip("/").split("/")
        res = self.reservations.get(parts[1]) if len(parts) > 1 else None
        if res is None:
            return httpx.Response(404, json={"detail": {"status": "error", "error": "Not found"}})
        if request.method == "GET":
            return httpx.Response(200, json={"status": "ok", "data": res})

        key = request.headers.get("Idempotency-Key")
        if key and key in self.idempotency:
            return httpx.Response(200, json={"status": "ok", "data": self.idempotency[key]})
        if res["status"] == "cancelled":
            return httpx.Response(409, json={"detail": {"status": "error", "error": "Reservation is cancelled"}})
        if parts[2] == "change":
            res["return_date"] = json.loads(request.content)["new_dropoff_date"]
        else:
            res["status"] = "cancelled"
        if key:
            self.idempotency[key] = dict(res)
        return httpx.Response(200, json={"status": "ok", "data": res})

    def writes(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method != "GET"]

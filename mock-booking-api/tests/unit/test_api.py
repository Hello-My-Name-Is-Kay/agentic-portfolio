"""Tests for the Mock Booking API. Each test gets a fresh in-memory database."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from booking_api.main import app

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("BOOKING_DB_PATH", ":memory:")
    monkeypatch.delenv("BOOKING_API_KEY", raising=False)
    with TestClient(app) as c:  # the context manager runs the lifespan (store + seed data)
        yield c


@pytest.fixture
def secured_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("BOOKING_DB_PATH", ":memory:")
    monkeypatch.setenv("BOOKING_API_KEY", "test-key")
    with TestClient(app) as c:
        yield c


def _error(resp_json: dict[str, object], code: str) -> None:
    assert resp_json["status"] == "error"
    assert resp_json["error_code"] == code
    assert isinstance(resp_json["error"], str)


class TestLookupCustomer:
    def test_lookup_existing_customer(self, client: TestClient) -> None:
        resp = client.get("/customers/C-00001")
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "data": {
                "id": "C-00001",
                "name": "Alice Johnson",
                "email": "alice@example.com",
                "phone": "555-0101",
                "drivers_license": "DL-USA-12345",
            },
            "error": None,
            "error_code": None,
        }

    def test_lookup_nonexistent_customer(self, client: TestClient) -> None:
        resp = client.get("/customers/C-99999")
        assert resp.status_code == 404
        _error(resp.json(), "NOT_FOUND")


class TestGetReservation:
    def test_get_seeded_reservation(self, client: TestClient) -> None:
        resp = client.get("/reservations/R-00001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["customer_id"] == "C-00001"
        assert data["return_date"] == "2025-11-07"
        assert data["status"] == "active"

    def test_get_nonexistent_reservation(self, client: TestClient) -> None:
        resp = client.get("/reservations/R-99999")
        assert resp.status_code == 404
        _error(resp.json(), "NOT_FOUND")


class TestChangeReservation:
    def test_change_dropoff_date(self, client: TestClient) -> None:
        resp = client.put("/reservations/R-00001/change", json={"new_dropoff_date": "2025-11-14"})
        assert resp.status_code == 200
        assert resp.json()["data"]["return_date"] == "2025-11-14"
        assert client.get("/reservations/R-00001").json()["data"]["return_date"] == "2025-11-14"

    def test_change_nonexistent(self, client: TestClient) -> None:
        resp = client.put("/reservations/R-99999/change", json={"new_dropoff_date": "2025-11-14"})
        assert resp.status_code == 404
        _error(resp.json(), "NOT_FOUND")

    def test_change_invalid_date(self, client: TestClient) -> None:
        resp = client.put("/reservations/R-00001/change", json={"new_dropoff_date": "not-a-date"})
        assert resp.status_code == 422
        _error(resp.json(), "BAD_INPUT")
        assert "new_dropoff_date" in resp.json()["error"]

    def test_change_before_pickup_rejected(self, client: TestClient) -> None:
        resp = client.put("/reservations/R-00001/change", json={"new_dropoff_date": "2025-10-30"})
        assert resp.status_code == 422
        _error(resp.json(), "BAD_INPUT")
        assert client.get("/reservations/R-00001").json()["data"]["return_date"] == "2025-11-07"

    def test_change_cancelled_reservation(self, client: TestClient) -> None:
        client.post("/reservations/R-00001/cancel")
        resp = client.put("/reservations/R-00001/change", json={"new_dropoff_date": "2025-11-14"})
        assert resp.status_code == 409
        _error(resp.json(), "INVALID_STATE")


class TestCancelReservation:
    def test_cancel_with_reason(self, client: TestClient) -> None:
        resp = client.post("/reservations/R-00001/cancel", json={"reason": "Changed plans"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelled"

    def test_cancel_twice_is_invalid_state(self, client: TestClient) -> None:
        assert client.post("/reservations/R-00001/cancel").status_code == 200
        resp = client.post("/reservations/R-00001/cancel")
        assert resp.status_code == 409
        _error(resp.json(), "INVALID_STATE")

    def test_cancel_nonexistent(self, client: TestClient) -> None:
        resp = client.post("/reservations/R-99999/cancel", json={})
        assert resp.status_code == 404
        _error(resp.json(), "NOT_FOUND")


class TestIdempotency:
    def test_cancel_replay_returns_original_response(self, client: TestClient) -> None:
        headers = {"Idempotency-Key": "cancel-1"}
        first = client.post("/reservations/R-00001/cancel", headers=headers)
        second = client.post("/reservations/R-00001/cancel", headers=headers)
        assert first.status_code == second.status_code == 200
        assert second.json() == first.json()

    def test_change_replay_does_not_reapply(self, client: TestClient) -> None:
        headers = {"Idempotency-Key": "change-1"}
        body = {"new_dropoff_date": "2025-11-14"}
        first = client.put("/reservations/R-00001/change", json=body, headers=headers)
        client.put("/reservations/R-00001/change", json={"new_dropoff_date": "2025-11-20"})
        replay = client.put("/reservations/R-00001/change", json=body, headers=headers)
        assert replay.json() == first.json()
        assert client.get("/reservations/R-00001").json()["data"]["return_date"] == "2025-11-20"

    def test_key_reused_for_different_request_conflicts(self, client: TestClient) -> None:
        headers = {"Idempotency-Key": "k-1"}
        client.put("/reservations/R-00001/change", json={"new_dropoff_date": "2025-11-14"}, headers=headers)
        resp = client.put("/reservations/R-00001/change", json={"new_dropoff_date": "2025-11-15"}, headers=headers)
        assert resp.status_code == 409
        _error(resp.json(), "IDEMPOTENCY_CONFLICT")
        resp = client.post("/reservations/R-00001/cancel", headers=headers)
        assert resp.status_code == 409


class TestHealthCheck:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["data"] == {"status": "healthy", "store_initialized": True}


class TestAPIKeyAuth:
    def test_open_when_no_key_configured(self, client: TestClient) -> None:
        assert client.get("/customers/C-00001").status_code == 200

    def test_missing_key_rejected(self, secured_client: TestClient) -> None:
        resp = secured_client.get("/customers/C-00001")
        assert resp.status_code == 401
        _error(resp.json(), "AUTH_FAILED")

    def test_wrong_key_rejected(self, secured_client: TestClient) -> None:
        resp = secured_client.get("/customers/C-00001", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_correct_key_accepted(self, secured_client: TestClient) -> None:
        resp = secured_client.get("/customers/C-00001", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200


class TestErrorsAndSpec:
    def test_store_not_initialized_without_lifespan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(app.state, "api_key", "", raising=False)
        monkeypatch.setattr(app.state, "store", None, raising=False)
        resp = TestClient(app).get("/customers/C-00001")
        assert resp.status_code == 500
        _error(resp.json(), "INTERNAL")

    @pytest.mark.usefixtures("client")
    def test_unhandled_exception_returns_envelope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(_customer_id: str) -> None:
            raise RuntimeError("db exploded")

        monkeypatch.setattr(app.state.store, "get_customer", boom)
        resp = TestClient(app, raise_server_exceptions=False).get("/customers/C-00001")
        assert resp.status_code == 500
        assert resp.json()["error"] == "Internal server error"

    def test_openapi_lists_endpoints(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert set(paths) == {
            "/customers/{customer_id}",
            "/reservations/{reservation_id}",
            "/reservations/{reservation_id}/change",
            "/reservations/{reservation_id}/cancel",
            "/health",
        }

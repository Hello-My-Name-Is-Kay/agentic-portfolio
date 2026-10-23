"""Tests for the MCP server tools."""

from __future__ import annotations

import json

import pytest
from mcp_server.server import (
    _get_reservation,
    _change_reservation,
    _cancel_reservation,
    GetReservationArgs,
    ChangeReservationArgs,
    CancelReservationArgs,
)


class TestGetReservation:
    """Tests for the get_reservation tool."""

    @pytest.mark.asyncio
    async def test_not_found_returns_error_json(self) -> None:
        result = await _get_reservation("R-99999")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "NOT_FOUND" or data["code"] == "UPSTREAM_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_invalid_id_format_returns_error(self) -> None:
        result = await _get_reservation("bad-id")
        data = json.loads(result)
        assert data["status"] == "error"

    def test_args_schema_validates_correctly(self) -> None:
        args = GetReservationArgs(reservation_id="R-00001")
        assert args.reservation_id == "R-00001"

    def test_args_schema_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            GetReservationArgs(reservation_id="")  # type: ignore[arg-type]


class TestChangeReservation:
    """Tests for the change_reservation tool."""

    @pytest.mark.asyncio
    async def test_not_found_returns_error_json(self) -> None:
        result = await _change_reservation("R-99999", "2025-11-14", "test-idem-001")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "NOT_FOUND" or data["code"] == "UPSTREAM_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_returns_structured_json(self) -> None:
        result = await _change_reservation("R-00001", "2025-11-14", "test-idem-002")
        data = json.loads(result)
        assert "status" in data
        assert data["status"] in ("ok", "error")

    def test_args_schema(self) -> None:
        args = ChangeReservationArgs(
            reservation_id="R-00001",
            new_dropoff_date="2025-11-14",
            idempotency_key="test-uuid",
        )
        assert args.idempotency_key == "test-uuid"


class TestCancelReservation:
    """Tests for the cancel_reservation tool."""

    @pytest.mark.asyncio
    async def test_not_found_returns_error_json(self) -> None:
        result = await _cancel_reservation("R-99999", "Testing", "test-idem-003")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "NOT_FOUND" or data["code"] == "UPSTREAM_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_returns_structured_json(self) -> None:
        result = await _cancel_reservation("R-00001", "Test cancellation", "test-idem-004")
        data = json.loads(result)
        assert "status" in data

    def test_args_schema(self) -> None:
        args = CancelReservationArgs(
            reservation_id="R-00001",
            reason="Changed my mind",
            idempotency_key="test-uuid",
        )
        assert args.reason == "Changed my mind"
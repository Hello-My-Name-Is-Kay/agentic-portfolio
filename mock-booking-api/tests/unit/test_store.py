"""Store-level tests (in-memory SQLite)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from booking_api.models import ReservationCreate, ReservationUpdate
from booking_api.store import BookingStore

if TYPE_CHECKING:
    from pathlib import Path


def _create(store: BookingStore, customer: str = "C-00001") -> dict[str, object]:
    return store.create_reservation(
        ReservationCreate(
            customer_id=customer,
            pickup_location_id="L-0001",
            return_location_id="L-0002",
            pickup_date=date(2025, 1, 1),
            return_date=date(2025, 1, 5),
            vehicle_category="SUV",
        )
    )


def test_sequential_ids_match_model_pattern() -> None:
    store = BookingStore(":memory:")
    assert [_create(store)["id"] for _ in range(3)] == ["R-00001", "R-00002", "R-00003"]


def test_list_reservations_filters_by_customer() -> None:
    store = BookingStore(":memory:")
    _create(store, "C-00001")
    _create(store, "C-00002")
    assert [r["customer_id"] for r in store.list_reservations("C-00002")] == ["C-00002"]
    assert len(store.list_reservations()) == 2


def test_update_only_given_fields() -> None:
    store = BookingStore(":memory:")
    _create(store)
    updated = store.update_reservation("R-00001", ReservationUpdate(new_vehicle_category="Compact"))
    assert updated is not None
    assert (updated["vehicle_category"], updated["return_date"]) == ("Compact", "2025-01-05")
    assert store.update_reservation("R-00009", ReservationUpdate(new_vehicle_category="X")) is None


def test_idempotency_record_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    import booking_api.store as store_module

    store = BookingStore(":memory:")
    monkeypatch.setattr(store_module.time, "time", lambda: 1000.0)
    store.put_idempotent("k", "fp", {"id": "R-00001"}, ttl_s=10)
    assert store.get_idempotent("k") == ("fp", {"id": "R-00001"})
    monkeypatch.setattr(store_module.time, "time", lambda: 1011.0)
    assert store.get_idempotent("k") is None


def test_file_database_persists(tmp_path: Path) -> None:
    path = str(tmp_path / "booking.db")
    store = BookingStore(path)
    _create(store)
    store.close()
    assert BookingStore(path).get_reservation("R-00001") is not None


def test_return_must_be_after_pickup() -> None:
    with pytest.raises(ValidationError, match="return_date must be after pickup_date"):
        ReservationCreate(
            customer_id="C-00001",
            pickup_location_id="L-0001",
            return_location_id="L-0001",
            pickup_date=date(2025, 1, 5),
            return_date=date(2025, 1, 5),
            vehicle_category="SUV",
        )

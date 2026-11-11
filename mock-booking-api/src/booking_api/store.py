"""SQLite storage for customers, reservations and idempotency records."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from booking_api.logging import get_logger

if TYPE_CHECKING:
    from booking_api.models import ReservationCreate, ReservationUpdate

log = get_logger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class BookingStore:
    """Persistent store for reservations and idempotency records.

    One SQLite connection shared across threads and guarded by a lock. Pass
    ``db_path=":memory:"`` for a throwaway database (used by the tests).
    """

    def __init__(self, db_path: str = "booking.db") -> None:
        """Open (or create) the database and its tables."""
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    pickup_location_id TEXT NOT NULL,
                    return_location_id TEXT NOT NULL,
                    pickup_date TEXT NOT NULL,
                    return_date TEXT NOT NULL,
                    vehicle_category TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS idempotency_records (
                    idem_key TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    response_data TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS customers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    drivers_license TEXT NOT NULL
                );
                """
            )

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # --- Customers ---

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        """Return a customer by ID, or None."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return dict(row) if row is not None else None

    def seed_customers(self, customers: list[dict[str, str]]) -> None:
        """Insert customers, skipping IDs that already exist."""
        with self._lock:
            self._conn.executemany(
                "INSERT OR IGNORE INTO customers VALUES (?, ?, ?, ?, ?)",
                [(c["id"], c["name"], c["email"], c["phone"], c["drivers_license"]) for c in customers],
            )
            self._conn.commit()

    # --- Reservations ---

    def get_reservation(self, reservation_id: str) -> dict[str, Any] | None:
        """Return a reservation by ID, or None."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_reservations(self, customer_id: str | None = None) -> list[dict[str, Any]]:
        """List reservations, newest first, optionally for one customer."""
        with self._lock:
            if customer_id:
                rows = self._conn.execute(
                    "SELECT * FROM reservations WHERE customer_id = ? ORDER BY created_at DESC", (customer_id,)
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM reservations ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def create_reservation(self, data: ReservationCreate) -> dict[str, Any]:
        """Create a reservation with the next sequential ID (R-00001, R-00002, ...)."""
        now = _now()
        with self._lock:
            row = self._conn.execute("SELECT MAX(CAST(SUBSTR(id, 3) AS INTEGER)) FROM reservations").fetchone()
            rid = f"R-{(row[0] or 0) + 1:05d}"
            self._conn.execute(
                """INSERT INTO reservations
                   (id, customer_id, pickup_location_id, return_location_id,
                    pickup_date, return_date, vehicle_category, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
                (
                    rid,
                    data.customer_id,
                    data.pickup_location_id,
                    data.return_location_id,
                    data.pickup_date.isoformat(),
                    data.return_date.isoformat(),
                    data.vehicle_category,
                    now,
                    now,
                ),
            )
            self._conn.commit()
        log.info("reservation.created", reservation_id=rid)
        return self.get_reservation(rid) or {}

    def update_reservation(self, reservation_id: str, data: ReservationUpdate) -> dict[str, Any] | None:
        """Apply the non-empty fields of ``data``; return the updated reservation or None if missing."""
        fields = {
            "pickup_date": data.new_pickup_date.isoformat() if data.new_pickup_date else None,
            "return_date": data.new_return_date.isoformat() if data.new_return_date else None,
            "vehicle_category": data.new_vehicle_category,
        }
        updates = {k: v for k, v in fields.items() if v is not None}
        if updates:  # column names come from the fixed dict above, values are bound parameters
            assignments = ", ".join(f"{column} = ?" for column in updates)
            with self._lock:
                self._conn.execute(
                    f"UPDATE reservations SET {assignments}, updated_at = ? WHERE id = ?",
                    [*updates.values(), _now(), reservation_id],
                )
                self._conn.commit()
        return self.get_reservation(reservation_id)

    def cancel_reservation(self, reservation_id: str) -> dict[str, Any] | None:
        """Mark a reservation cancelled; return it, or None if missing."""
        with self._lock:
            self._conn.execute(
                "UPDATE reservations SET status = 'cancelled', updated_at = ? WHERE id = ?", (_now(), reservation_id)
            )
            self._conn.commit()
        return self.get_reservation(reservation_id)

    # --- Idempotency ---

    def get_idempotent(self, idem_key: str) -> tuple[str, dict[str, Any]] | None:
        """Return (fingerprint, stored response) for an unexpired key, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT fingerprint, response_data, expires_at FROM idempotency_records WHERE idem_key = ?",
                (idem_key,),
            ).fetchone()
            if row is None:
                return None
            if row["expires_at"] < time.time():
                self._conn.execute("DELETE FROM idempotency_records WHERE idem_key = ?", (idem_key,))
                self._conn.commit()
                return None
        return row["fingerprint"], json.loads(row["response_data"])

    def put_idempotent(
        self, idem_key: str, fingerprint: str, response_data: dict[str, Any], ttl_s: int = 86400
    ) -> None:
        """Store the response for a key, tied to the request fingerprint, for ``ttl_s`` seconds."""
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO idempotency_records VALUES (?, ?, ?, ?)",
                (idem_key, fingerprint, json.dumps(response_data), time.time() + ttl_s),
            )
            self._conn.commit()

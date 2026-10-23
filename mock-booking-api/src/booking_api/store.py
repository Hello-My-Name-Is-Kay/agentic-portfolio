"""In-memory + SQLite storage for reservations and idempotency keys."""

from __future__ import annotations

import json
from booking_api.logging import get_logger
import sqlite3
import threading
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from booking_api.errors import IdempotencyConflict, NotFoundError
from booking_api.models import Reservation, ReservationCreate, ReservationUpdate

log = get_logger(__name__)


class BookingStore:
    """Persistent store for reservations and idempotency records.

    Uses SQLite with WAL mode for safe concurrent access.
    Falls back to in-memory dict for testing when path is ':memory:'.
    """

    def __init__(self, db_path: str = "booking.db") -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.row_factory = sqlite3.Row
            self._init_db()
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
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
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS idempotency_store (
                idem_key TEXT PRIMARY KEY,
                response_data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                drivers_license TEXT NOT NULL
            )
        """)
        conn.commit()

    # --- Customers ---

    def get_customer(self, customer_id: str) -> dict | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def seed_customers(self, customers: list[dict]) -> None:
        conn = self._get_conn()
        for c in customers:
            conn.execute(
                "INSERT OR IGNORE INTO customers VALUES (?, ?, ?, ?, ?)",
                (c["id"], c["name"], c["email"], c["phone"], c["drivers_license"]),
            )
        conn.commit()

    # --- Reservations ---
    def _row_to_reservation(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "customer_id": row["customer_id"],
            "pickup_location_id": row["pickup_location_id"],
            "return_location_id": row["return_location_id"],
            "pickup_date": row["pickup_date"],
            "return_date": row["return_date"],
            "vehicle_category": row["vehicle_category"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_reservation(self, reservation_id: str) -> dict | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM reservations WHERE id = ?", (reservation_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_reservation(row)

    def list_reservations(self, customer_id: str | None = None) -> list[dict]:
        conn = self._get_conn()
        if customer_id:
            rows = conn.execute(
                "SELECT * FROM reservations WHERE customer_id = ? ORDER BY created_at DESC",
                (customer_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reservations ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_reservation(r) for r in rows]

    def create_reservation(self, data: ReservationCreate) -> dict:
        conn = self._get_conn()
        rid = f"R-{uuid.uuid4().hex[:5].upper()}"
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO reservations
               (id, customer_id, pickup_location_id, return_location_id,
                pickup_date, return_date, vehicle_category, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (rid, data.customer_id, data.pickup_location_id, data.return_location_id,
             data.pickup_date.isoformat(), data.return_date.isoformat(),
             data.vehicle_category, now, now),
        )
        conn.commit()
        return self.get_reservation(rid)  # type: ignore[return-value]

    def update_reservation(self, reservation_id: str, data: ReservationUpdate) -> dict | None:
        conn = self._get_conn()
        existing = self.get_reservation(reservation_id)
        if existing is None:
            return None

        updates: list[str] = []
        params: list[Any] = []
        now = datetime.utcnow().isoformat()

        if data.new_pickup_date:
            updates.append("pickup_date = ?")
            params.append(data.new_pickup_date.isoformat())
        if data.new_return_date:
            updates.append("return_date = ?")
            params.append(data.new_return_date.isoformat())
        if data.new_vehicle_category:
            updates.append("vehicle_category = ?")
            params.append(data.new_vehicle_category)
        updates.append("updated_at = ?")
        params.append(now)
        params.append(reservation_id)

        if len(updates) > 1:  # more than just updated_at
            conn.execute(
                f"UPDATE reservations SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()

        return self.get_reservation(reservation_id)

    def cancel_reservation(self, reservation_id: str) -> dict | None:
        conn = self._get_conn()
        existing = self.get_reservation(reservation_id)
        if existing is None:
            return None
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE reservations SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (now, reservation_id),
        )
        conn.commit()
        return self.get_reservation(reservation_id)

    # --- Idempotency ---

    def get_idempotent(self, idem_key: str) -> dict | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT response_data FROM idempotency_store WHERE idem_key = ?",
            (idem_key,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["response_data"])

    def put_idempotent(self, idem_key: str, response_data: dict, ttl_s: int = 86400) -> None:
        conn = self._get_conn()
        expiry = time.time() + ttl_s
        conn.execute(
            "INSERT OR REPLACE INTO idempotency_store VALUES (?, ?, ?)",
            (idem_key, json.dumps(response_data), expiry),
        )
        conn.commit()
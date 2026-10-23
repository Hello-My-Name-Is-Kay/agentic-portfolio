"""Pydantic models for the booking API request/response bodies."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class Customer(BaseModel):
    """A customer of the rental company."""

    id: str = Field(pattern=r"^C-\d{5}$")
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")
    phone: str = Field(min_length=7, max_length=20)
    drivers_license: str = Field(min_length=5, max_length=30)


class Address(BaseModel):
    """An address for a rental location."""

    street: str = Field(min_length=1)
    city: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    zip_code: str = Field(pattern=r"^\d{5}$")


class Location(BaseModel):
    """A rental location."""

    id: str = Field(pattern=r"^L-\d{4}$")
    name: str = Field(min_length=1)
    address: Address


class ReservationStatus(str):
    """Reservation status enum."""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class ReservationCreate(BaseModel):
    """Request body to create a reservation."""

    customer_id: str = Field(pattern=r"^C-\d{5}$")
    pickup_location_id: str = Field(pattern=r"^L-\d{4}$")
    return_location_id: str = Field(pattern=r"^L-\d{4}$")
    pickup_date: date
    return_date: date
    vehicle_category: str = Field(min_length=1)

    @field_validator("return_date")
    @classmethod
    def return_after_pickup(cls, v: date, info) -> date:  # type: ignore[no-untyped-def]
        pickup = info.data.get("pickup_date")
        if pickup and v <= pickup:
            raise ValueError("return_date must be after pickup_date")
        return v


class ReservationUpdate(BaseModel):
    """Request body to update a reservation's dates."""

    new_pickup_date: date | None = None
    new_return_date: date | None = None
    new_vehicle_category: str | None = None


class Reservation(BaseModel):
    """A car rental reservation."""

    id: str = Field(pattern=r"^R-\d{5}$")
    customer_id: str = Field(pattern=r"^C-\d{5}$")
    pickup_location_id: str = Field(pattern=r"^L-\d{4}$")
    return_location_id: str = Field(pattern=r"^L-\d{4}$")
    pickup_date: date
    return_date: date
    vehicle_category: str
    status: str = Field(default="active", pattern=r"^(active|cancelled|completed|no_show)$")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChangeReservationRequest(BaseModel):
    """Request body for changing a reservation's drop-off date."""

    new_dropoff_date: date
    reason: str | None = None


class CancelReservationRequest(BaseModel):
    """Request body for cancelling a reservation."""

    reason: str | None = None


class ApiResponse(BaseModel):
    """Standard API response wrapper."""

    status: str = Field(pattern=r"^(ok|error)$")
    data: dict | None = None
    error: str | None = None
    error_code: str | None = None
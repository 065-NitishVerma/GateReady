from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_BOOKINGS: list[dict[str, Any]] = [
    {
        "_id": "booking_101",
        "user_id": "user_123",
        "flight_number": "AI-888",
        "origin": "Pune",
        "destination": "Delhi",
        "date": "2026-03-10T14:00:00Z",
        "status": "Confirmed",
    },
    {
        "_id": "booking_102",
        "user_id": "user_123",
        "flight_number": "AI-999",
        "origin": "Delhi",
        "destination": "Mumbai",
        "date": "2026-04-01T09:30:00Z",
        "status": "Confirmed",
    },
]


def _parse_iso(dt: str) -> datetime:
    if dt.endswith("Z"):
        dt = dt[:-1] + "+00:00"
    return datetime.fromisoformat(dt).astimezone(timezone.utc)


def find_latest_booking(user_id: str) -> dict[str, Any] | None:
    matches = [b for b in _BOOKINGS if b.get("user_id") == user_id]
    if not matches:
        return None
    return max(matches, key=lambda b: _parse_iso(b["date"]))

from __future__ import annotations

import os
from typing import Any

import httpx

from app.db import get_bookings_collection


def get_latest_booking_db(user_id: str) -> dict[str, Any] | None:
    if not user_id:
        return None
    collection = get_bookings_collection()
    return collection.find_one({"user_id": user_id}, sort=[("date", -1)])


async def get_latest_booking_via_api(access_token: str) -> dict[str, Any] | None:
    if not access_token:
        return None
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    # API-first: booking lookup goes through HTTP so auth/audit stays in one layer.
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{base_url}/bookings/latest",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code != 200:
            return None
        return resp.json()
    except httpx.HTTPError:
        return None


async def get_all_bookings_via_api(access_token: str) -> list[dict[str, Any]]:
    if not access_token:
        return []
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{base_url}/bookings",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data if isinstance(data, list) else []
    except httpx.HTTPError:
        return []


async def get_booking_by_flight_via_api(access_token: str, flight_number: str) -> dict[str, Any] | None:
    if not access_token or not flight_number:
        return None
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{base_url}/bookings/flight/{flight_number}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code != 200:
            return None
        return resp.json()
    except httpx.HTTPError:
        return None


async def get_flight_info_via_api(access_token: str, flight_number: str) -> dict[str, Any] | None:
    if not access_token or not flight_number:
        return None
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{base_url}/flight-info/{flight_number}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code != 200:
            return None
        return resp.json()
    except httpx.HTTPError:
        return None

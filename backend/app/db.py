from __future__ import annotations

import os
from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    uri = _require_env("MONGODB_URI")
    return MongoClient(uri)


@lru_cache(maxsize=1)
def get_db() -> Database:
    db_name = os.getenv("MONGODB_DB_NAME", "booking_assistant")
    return get_client()[db_name]


def get_bookings_collection() -> Collection:
    name = os.getenv("MONGODB_BOOKINGS_COLLECTION", "bookings")
    return get_db()[name]


def get_users_collection() -> Collection:
    name = os.getenv("MONGODB_USERS_COLLECTION", "users")
    return get_db()[name]


def get_flight_info_collection() -> Collection:
    name = os.getenv("MONGODB_FLIGHT_INFO_COLLECTION", "flight_info")
    return get_db()[name]

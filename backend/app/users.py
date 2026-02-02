from __future__ import annotations

from dataclasses import dataclass

from passlib.context import CryptContext

from app.db import get_users_collection


_PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@dataclass(frozen=True)
class UserRecord:
    user_id: str
    username: str
    password_hash: str


def _to_user_record(doc: dict | None) -> UserRecord | None:
    if not doc:
        return None
    return UserRecord(
        user_id=str(doc.get("user_id", "")),
        username=str(doc.get("username", "")),
        password_hash=str(doc.get("password_hash", "")),
    )


def get_user_by_username(username: str) -> UserRecord | None:
    collection = get_users_collection()
    doc = collection.find_one({"username": username})
    return _to_user_record(doc)


def get_user_by_id(user_id: str) -> UserRecord | None:
    if not user_id:
        return None
    collection = get_users_collection()
    doc = collection.find_one({"user_id": user_id})
    return _to_user_record(doc)


def create_user(user_id: str, username: str, password: str) -> UserRecord:
    collection = get_users_collection()
    password_hash = _PWD_CONTEXT.hash(password)
    collection.insert_one(
        {"user_id": user_id, "username": username, "password_hash": password_hash}
    )
    return UserRecord(user_id=user_id, username=username, password_hash=password_hash)


def ensure_demo_user() -> None:
    if get_user_by_username("user_123"):
        return
    create_user(user_id="user_123", username="user_123", password="demo-pass")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _PWD_CONTEXT.verify(plain_password, password_hash)

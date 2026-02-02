from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from dataclasses import dataclass

import jwt
from jwt import InvalidTokenError


@dataclass(frozen=True)
class AuthResult:
    user_id: str | None
    is_authenticated: bool
    token_id: str | None = None


def _jwt_secret() -> str:
    return os.getenv("JWT_SECRET", "dev-secret")


def _jwt_refresh_secret() -> str:
    return os.getenv("JWT_REFRESH_SECRET", "dev-refresh-secret")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _access_ttl_minutes() -> int:
    return int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "15"))


def _refresh_ttl_days() -> int:
    return int(os.getenv("REFRESH_TOKEN_TTL_DAYS", "7"))


def decode_bearer_token(auth_header: str | None) -> AuthResult:
    if not auth_header:
        return AuthResult(user_id=None, is_authenticated=False)

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return AuthResult(user_id=None, is_authenticated=False)

    token = parts[1]
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except InvalidTokenError:
        return AuthResult(user_id=None, is_authenticated=False)

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        return AuthResult(user_id=None, is_authenticated=False)

    return AuthResult(user_id=user_id, is_authenticated=True)


def create_token(user_id: str) -> str:
    now = _now_utc()
    payload = {
        "sub": user_id,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=_access_ttl_minutes())).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    now = _now_utc()
    token_id = uuid4().hex
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": token_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=_refresh_ttl_days())).timestamp()),
    }
    return jwt.encode(payload, _jwt_refresh_secret(), algorithm="HS256")


def decode_refresh_token(token: str | None) -> AuthResult:
    if not token:
        return AuthResult(user_id=None, is_authenticated=False)
    try:
        payload = jwt.decode(token, _jwt_refresh_secret(), algorithms=["HS256"])
    except InvalidTokenError:
        return AuthResult(user_id=None, is_authenticated=False)
    if payload.get("type") != "refresh":
        return AuthResult(user_id=None, is_authenticated=False)
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        return AuthResult(user_id=None, is_authenticated=False)
    token_id = payload.get("jti")
    if not isinstance(token_id, str) or not token_id:
        return AuthResult(user_id=None, is_authenticated=False)
    return AuthResult(user_id=user_id, is_authenticated=True, token_id=token_id)

"""Passwords (Argon2id) and tokens (signed JWTs: a short-lived access token and a refresh token)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from clearhire.config import Settings

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("timing-equaliser")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant work whether or not the user exists, so login timing reveals nothing."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def issue_token(settings: Settings, user_id: uuid.UUID, role: str, kind: str = "access") -> str:
    now = datetime.now(UTC)
    ttl = (
        timedelta(minutes=settings.access_ttl_minutes)
        if kind == "access"
        else timedelta(days=settings.refresh_ttl_days)
    )
    claims = {
        "sub": str(user_id),
        "role": role,
        "typ": kind,
        "iat": now,
        "exp": now + ttl,
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def read_token(settings: Settings, token: str, kind: str = "access") -> dict[str, Any]:
    """The token's claims; raises jwt.InvalidTokenError if it is forged, expired or the wrong kind."""
    claims: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        options={"require": ["exp", "sub", "typ"]},
    )
    if claims.get("typ") != kind:
        raise jwt.InvalidTokenError("wrong token type")
    return claims


def status_token() -> str:
    """The secret in a candidate's status link."""
    return secrets.token_urlsafe(24)

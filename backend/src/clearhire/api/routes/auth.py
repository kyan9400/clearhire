from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from clearhire import audit
from clearhire.api.deps import CurrentUser, Session, Shared
from clearhire.api.schemas import LoginIn, RefreshIn, TokenOut, UserOut
from clearhire.db.models import User
from clearhire.security import issue_token, read_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _tokens(services: Shared, user: User) -> TokenOut:
    settings = services.settings
    return TokenOut(
        access_token=issue_token(settings, user.id, user.role.value),
        refresh_token=issue_token(settings, user.id, user.role.value, kind="refresh"),
        user=UserOut.model_validate(user),
    )


@router.post("/login")
async def login(body: LoginIn, session: Session, services: Shared) -> TokenOut:
    user = (await session.execute(select(User).where(func.lower(User.email) == body.email.lower()))).scalar()
    if (
        not verify_password(body.password, user.password_hash if user else None)
        or user is None
        or not user.active
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong e-mail or password")
    await audit.record(session, "user.login", "user", user.id, actor_id=user.id)
    await session.commit()
    return _tokens(services, user)


@router.post("/refresh")
async def refresh(body: RefreshIn, session: Session, services: Shared) -> TokenOut:
    try:
        claims = read_token(services.settings, body.refresh_token, kind="refresh")
        user = await session.get(User, uuid.UUID(claims["sub"]))
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired refresh token") from exc
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account disabled")
    return _tokens(services, user)


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)

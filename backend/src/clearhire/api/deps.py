"""FastAPI dependencies: the database session, shared services, the signed-in user and role checks."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from clearhire.db.models import Role, User
from clearhire.db.session import sessions
from clearhire.security import read_token
from clearhire.services.pipeline import Services

_bearer = HTTPBearer(auto_error=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with sessions()() as session:
        yield session


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


Session = Annotated[AsyncSession, Depends(get_session)]
Shared = Annotated[Services, Depends(get_services)]


async def current_user(
    session: Session,
    services: Shared,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "sign in first", headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        claims = read_token(services.settings, credentials.credentials)
        user = await session.get(User, uuid.UUID(claims["sub"]))
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token") from exc
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account disabled")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require(*roles: Role) -> Callable[..., Coroutine[Any, Any, User]]:
    async def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "your role cannot do this")
        return user

    return check


def writable(services: Shared) -> None:
    if services.settings.demo_read_only:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this is a read-only demo")


Staff = Annotated[User, Depends(require(Role.ADMIN, Role.RECRUITER, Role.HIRING_MANAGER))]
Recruiter = Annotated[User, Depends(require(Role.ADMIN, Role.RECRUITER))]
Admin = Annotated[User, Depends(require(Role.ADMIN))]
Writable = Depends(writable)


def sees_personal_data(user: User, blind: bool) -> bool:
    """Hiring managers always review blind; recruiters and admins may switch blind mode off."""
    return not blind and user.role in (Role.ADMIN, Role.RECRUITER)


def pseudonym(candidate_id: uuid.UUID) -> str:
    return f"Candidate {candidate_id.hex[:4].upper()}"

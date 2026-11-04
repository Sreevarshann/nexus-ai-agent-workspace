"""Request dependencies: database session and authenticated user."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.db import get_db
from nexus.models import ApiToken, User
from nexus.models import Session as UserSession
from nexus.security import token_digest

SESSION_COOKIE = "nexus_session"

DB = Annotated[AsyncSession, Depends(get_db)]


async def resolve_user(db: AsyncSession, session_token: str | None, bearer: str | None) -> User | None:
    now = datetime.now(UTC)
    if session_token:
        row = await db.get(UserSession, token_digest(session_token))
        if row and row.expires_at > now:
            return await db.get(User, row.user_id)
    if bearer:
        tok = (await db.execute(select(ApiToken).where(ApiToken.token_hash == token_digest(bearer)))).scalar()
        if tok:
            tok.last_used_at = now
            await db.commit()
            return await db.get(User, tok.user_id)
    return None


async def current_user(
    db: DB,
    nexus_session: Annotated[str | None, Cookie()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    bearer = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None
    user = await resolve_user(db, nexus_session, bearer)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def not_found(what: str = "Resource") -> HTTPException:
    # Same response for "missing" and "belongs to someone else" so ids cannot be probed.
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")

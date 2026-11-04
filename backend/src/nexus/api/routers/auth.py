"""Account registration, login and session management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from nexus.api.deps import DB, SESSION_COOKIE, CurrentUser
from nexus.config import get_settings
from nexus.models import ApiToken, Project, User, Workspace
from nexus.models import Session as UserSession
from nexus.ratelimit import enforce
from nexus.security import hash_password, new_token, token_digest, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
# Local-first: accept reserved domains such as .local/.test that strict email validators reject.
Email = Annotated[str, Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
SESSION_TTL = timedelta(days=14)


class RegisterIn(BaseModel):
    email: Email
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=256)


class LoginIn(BaseModel):
    email: Email
    password: str = Field(max_length=256)


class UserOut(BaseModel):
    id: str
    email: str
    name: str

    @classmethod
    def of(cls, u: User) -> UserOut:
        return cls(id=str(u.id), email=u.email, name=u.name)


async def _start_session(db: DB, response: Response, user: User) -> None:
    token = new_token()
    db.add(UserSession(token_hash=token_digest(token), user_id=user.id, expires_at=datetime.now(UTC) + SESSION_TTL))
    await db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=get_settings().env == "production",
        path="/",
    )


async def create_user(db: DB, email: str, name: str, password: str) -> User:
    user = User(email=email.lower(), name=name, password_hash=hash_password(password))
    db.add(user)
    await db.flush()
    ws = Workspace(user_id=user.id, name=f"{name}'s workspace")
    db.add(ws)
    await db.flush()
    db.add(Project(user_id=user.id, workspace_id=ws.id, name="General", description="Default project"))
    await db.commit()
    return user


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterIn, request: Request, response: Response, db: DB) -> UserOut:
    await enforce(f"register:{request.client.host if request.client else 'x'}", 10, 3600)
    exists = await db.scalar(select(func.count()).select_from(User).where(User.email == body.email.lower()))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = await create_user(db, body.email, body.name, body.password)
    await _start_session(db, response, user)
    return UserOut.of(user)


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, request: Request, response: Response, db: DB) -> UserOut:
    await enforce(f"login:{body.email.lower()}", 10, 300)
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar()
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    await _start_session(db, response, user)
    return UserOut.of(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: DB) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await db.execute(delete(UserSession).where(UserSession.token_hash == token_digest(token)))
        await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.of(user)


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("/tokens")
async def list_tokens(user: CurrentUser, db: DB) -> list[dict[str, object]]:
    rows = (
        await db.execute(select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc()))
    ).scalars()
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "prefix": t.prefix,
            "created_at": t.created_at,
            "last_used_at": t.last_used_at,
        }
        for t in rows
    ]


@router.post("/tokens", status_code=201)
async def create_token(body: TokenIn, user: CurrentUser, db: DB) -> dict[str, str]:
    """Create an API token for MCP clients. The plaintext is shown exactly once."""
    token = new_token("nxs_")
    db.add(ApiToken(user_id=user.id, name=body.name, prefix=token[:10], token_hash=token_digest(token), scopes=["mcp"]))
    await db.commit()
    return {"token": token, "prefix": token[:10]}


@router.delete("/tokens/{token_id}", status_code=204)
async def revoke_token(token_id: str, user: CurrentUser, db: DB) -> None:
    await db.execute(delete(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id))
    await db.commit()

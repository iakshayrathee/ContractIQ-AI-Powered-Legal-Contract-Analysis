"""
app/auth/router.py
===================
Authentication endpoints:
  POST /auth/register  — create a new user account
  POST /auth/login     — exchange credentials for tokens
  POST /auth/refresh   — exchange refresh cookie for new access token
  POST /auth/logout    — clear the refresh cookie

Token strategy:
  Access token  — short-lived JWT (default 60 min), sent as Bearer in Authorization header.
                  Stored in React context / memory only (never localStorage).
  Refresh token — long-lived JWT (default 7 days), sent as httpOnly SameSite=Strict cookie.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_session_factory
from app.db.models import UserRow

router = APIRouter(prefix="/auth", tags=["Auth"])

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

REFRESH_TOKEN_EXPIRE_DAYS = 7
REFRESH_COOKIE_NAME = "refresh_token"


# ---------------------------------------------------------------------------
# Pydantic schemas (local — not shared with other modules)
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _create_token(subject: str, email: str, expire_minutes: int, secret: str, algorithm: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def _create_refresh_token(subject: str, secret: str, algorithm: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=False,      # set to True behind HTTPS in production
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/auth/refresh",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(body: RegisterRequest) -> dict:
    """
    Create a new user with the given email and password.

    Returns 409 Conflict if the email is already registered.
    """
    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        existing = await session.execute(
            select(UserRow).where(UserRow.email == body.email)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        user = UserRow(
            id=str(uuid.uuid4()),
            email=body.email,
            hashed_password=_hash_password(body.password),
        )
        session.add(user)
        await session.commit()

    return {"message": "Account created. Please log in."}


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and obtain access + refresh tokens",
)
async def login(body: LoginRequest, response: Response) -> TokenResponse:
    """
    Validate credentials and return:
      - access_token in the JSON body (Bearer, short-lived)
      - refresh_token as an httpOnly SameSite=Strict cookie (long-lived)
    """
    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            select(UserRow).where(UserRow.email == body.email)
        )
        user: UserRow | None = result.scalar_one_or_none()

    if user is None or not _verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    access_token = _create_token(
        subject=user.id,
        email=user.email,
        expire_minutes=settings.jwt_expire_minutes,
        secret=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    refresh_token = _create_refresh_token(
        subject=user.id,
        secret=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(access_token=access_token)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Issue a new access token using the refresh cookie",
)
async def refresh_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> TokenResponse:
    """
    Read the httpOnly refresh cookie and issue a new short-lived access token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token missing or invalid.",
    )
    if refresh_token is None:
        raise credentials_exception

    settings = get_settings()
    from jose import JWTError

    try:
        payload = jwt.decode(
            refresh_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Fetch user email for the new access token
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(UserRow).where(UserRow.id == user_id)
        )
        user: UserRow | None = result.scalar_one_or_none()
        if user is None:
            raise credentials_exception

    new_access = _create_token(
        subject=user_id,
        email=user.email,
        expire_minutes=settings.jwt_expire_minutes,
        secret=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return TokenResponse(access_token=new_access)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout — clear the refresh cookie",
)
async def logout(response: Response) -> None:
    """Clear the refresh cookie (client must also discard the access token from memory)."""
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/auth/refresh")

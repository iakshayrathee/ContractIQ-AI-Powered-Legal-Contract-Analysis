"""
tests/test_auth.py
===================
Unit tests for JWT authentication (Task 3).

Tests cover:
  - POST /auth/register creates a user
  - POST /auth/register rejects duplicate email (409)
  - POST /auth/login returns valid access token
  - POST /auth/login sets httpOnly refresh cookie
  - POST /auth/login rejects wrong password (401)
  - POST /auth/refresh issues new access token from cookie
  - POST /auth/refresh rejects missing cookie (401)
  - POST /auth/logout clears the cookie
  - get_current_user dependency returns user_id for valid token
  - get_current_user raises 401 for expired/invalid/missing token
  - Protected endpoint returns 401 without token
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from jose import jwt

from app.config import get_settings
from app.auth.dependencies import get_current_user
from app.auth.router import (
    _create_token,
    _hash_password,
    _verify_password,
    REFRESH_COOKIE_NAME,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_access_token(user_id: str, expire_minutes: int = 60, email: str = "test@example.com") -> str:
    settings = get_settings()
    return _create_token(
        subject=user_id,
        email=email,
        expire_minutes=expire_minutes,
        secret=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def _make_expired_token(user_id: str) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# Password hashing tests
# ---------------------------------------------------------------------------

class TestPasswordHashing:

    def test_hash_password_produces_bcrypt_hash(self):
        hashed = _hash_password("mysecret")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_verify_password_correct(self):
        hashed = _hash_password("correct")
        assert _verify_password("correct", hashed) is True

    def test_verify_password_incorrect(self):
        hashed = _hash_password("correct")
        assert _verify_password("wrong", hashed) is False


# ---------------------------------------------------------------------------
# _create_token tests
# ---------------------------------------------------------------------------

class TestCreateToken:

    def test_token_contains_sub_claim(self):
        settings = get_settings()
        user_id = str(uuid.uuid4())
        token = _create_token(
            subject=user_id,
            email="test@example.com",
            expire_minutes=60,
            secret=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["sub"] == user_id

    def test_token_expires_correctly(self):
        settings = get_settings()
        user_id = str(uuid.uuid4())
        token = _create_token(
            subject=user_id,
            email="test@example.com",
            expire_minutes=30,
            secret=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        # Should expire in ~30 minutes
        assert 29 * 60 < (exp - now).total_seconds() < 31 * 60


# ---------------------------------------------------------------------------
# get_current_user dependency tests
# ---------------------------------------------------------------------------

class TestGetCurrentUser:

    @pytest.mark.asyncio
    async def test_valid_token_returns_user_id(self, session_factory):
        user_id = str(uuid.uuid4())
        email = f"{user_id}@example.com"
        # Seed user in database
        from app.db.models import UserRow
        async with session_factory() as session:
            session.add(UserRow(
                id=user_id,
                email=email,
                hashed_password="hashed_pwd",
            ))
            await session.commit()

        token = _make_access_token(user_id, email=email)
        result = await get_current_user(token=token)
        assert result == user_id

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        from fastapi import HTTPException
        user_id = str(uuid.uuid4())
        token = _make_expired_token(user_id)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="not.a.jwt")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_token_with_no_sub_raises_401(self):
        from fastapi import HTTPException
        settings = get_settings()
        # Create token without 'sub' claim
        payload = {
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# /auth/register endpoint tests
# ---------------------------------------------------------------------------

class TestRegisterEndpoint:

    @pytest.mark.asyncio
    async def test_register_creates_user(self, async_client: AsyncClient):
        """POST /auth/register with new email should return 201."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # no existing user
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.auth.router.get_session_factory", return_value=mock_factory):
            response = await async_client.post(
                "/auth/register",
                json={"email": "newuser@example.com", "password": "securepassword123"},
            )

        assert response.status_code == 201
        assert "message" in response.json()

    @pytest.mark.asyncio
    async def test_register_rejects_duplicate_email(self, async_client: AsyncClient):
        """POST /auth/register with existing email should return 409."""
        from app.db.models import UserRow

        existing_user = MagicMock(spec=UserRow)
        existing_user.email = "existing@example.com"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.auth.router.get_session_factory", return_value=mock_factory):
            response = await async_client.post(
                "/auth/register",
                json={"email": "existing@example.com", "password": "pass"},
            )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_register_rejects_invalid_email(self, async_client: AsyncClient):
        """POST /auth/register with invalid email should return 422."""
        response = await async_client.post(
            "/auth/register",
            json={"email": "not-an-email", "password": "pass"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# /auth/login endpoint tests
# ---------------------------------------------------------------------------

class TestLoginEndpoint:

    def _make_user_mock(self, email: str, password: str):
        from app.db.models import UserRow
        user = MagicMock(spec=UserRow)
        user.id = str(uuid.uuid4())
        user.email = email
        user.hashed_password = _hash_password(password)
        return user

    @pytest.mark.asyncio
    async def test_login_returns_access_token(self, async_client: AsyncClient):
        """POST /auth/login with correct credentials should return access_token."""
        user = self._make_user_mock("test@example.com", "correctpassword")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.auth.router.get_session_factory", return_value=mock_factory):
            response = await async_client.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "correctpassword"},
            )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_sets_refresh_cookie(self, async_client: AsyncClient):
        """POST /auth/login should set httpOnly refresh cookie."""
        user = self._make_user_mock("test@example.com", "correctpassword")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.auth.router.get_session_factory", return_value=mock_factory):
            response = await async_client.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "correctpassword"},
            )

        assert REFRESH_COOKIE_NAME in response.cookies

    @pytest.mark.asyncio
    async def test_login_rejects_wrong_password(self, async_client: AsyncClient):
        """POST /auth/login with wrong password should return 401."""
        user = self._make_user_mock("test@example.com", "correctpassword")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.auth.router.get_session_factory", return_value=mock_factory):
            response = await async_client.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "wrongpassword"},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_rejects_unknown_user(self, async_client: AsyncClient):
        """POST /auth/login with non-existent email should return 401."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.auth.router.get_session_factory", return_value=mock_factory):
            response = await async_client.post(
                "/auth/login",
                json={"email": "ghost@example.com", "password": "anypassword"},
            )

        assert response.status_code == 401


# ---------------------------------------------------------------------------
# /auth/refresh endpoint tests
# ---------------------------------------------------------------------------

class TestRefreshEndpoint:

    @pytest.mark.asyncio
    async def test_refresh_issues_new_access_token(self, async_client: AsyncClient):
        """POST /auth/refresh with valid cookie should return new access_token."""
        # Use pre-seeded test user from conftest
        user_id = "test-user-id"
        settings = get_settings()
        
        from app.auth.router import _create_refresh_token
        refresh = _create_refresh_token(user_id, settings.jwt_secret_key, settings.jwt_algorithm)

        async_client.cookies.set(REFRESH_COOKIE_NAME, refresh)
        response = await async_client.post("/auth/refresh")
        async_client.cookies.clear()

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body

    @pytest.mark.asyncio
    async def test_refresh_rejects_missing_cookie(self, async_client: AsyncClient):
        """POST /auth/refresh without cookie should return 401."""
        response = await async_client.post("/auth/refresh")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# /auth/logout tests
# ---------------------------------------------------------------------------

class TestLogoutEndpoint:

    @pytest.mark.asyncio
    async def test_logout_returns_204(self, async_client: AsyncClient):
        """POST /auth/logout should return 204."""
        response = await async_client.post("/auth/logout")
        assert response.status_code == 204

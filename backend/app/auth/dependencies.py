"""
app/auth/dependencies.py
=========================
FastAPI dependency for JWT access token validation.

Access tokens are short-lived Bearer tokens sent in the Authorization header.
Refresh tokens are httpOnly SameSite=Strict cookies set by /auth/login
and consumed by /auth/refresh (see router.py).
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """
    Validate the Bearer JWT, check database existence, and return the subject (user_id UUID string).

    Raises HTTP 401 for:
      - Missing / malformed token
      - Signature validation failure
      - Expired token
      - No 'sub' claim
      - User not found in database
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Check database presence
    from sqlalchemy import select
    from app.db.database import get_session_factory
    from app.db.models import UserRow

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(UserRow).where(UserRow.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise credentials_exception

    return user_id

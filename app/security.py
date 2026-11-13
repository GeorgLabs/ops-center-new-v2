"""Passwords, login tokens and the "current user" dependency."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from app.config import get_settings
from app.db import SessionDep
from app.models import User

# Argon2 - the current recommendation for storing passwords (slow on purpose, salted automatically).
password_hash = PasswordHash.recommended()

# A hash of a password nobody knows. Login checks it when the username does not exist, so
# "unknown user" and "wrong password" take the same time (user enumeration).
DUMMY_HASH = password_hash.hash("this-is-not-a-real-password")

# Makes the green "Authorize" button appear in /docs and tells FastAPI where to log in.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)


def create_access_token(user_id: int, token_version: int = 0) -> str:
    """A signed JWT. Claims: sub = user id (as text), ver = the user's token_version, iat, exp."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> tuple[int, int] | None:
    """(user id, token version) of a valid token, or None. Never raises, never trusts the token's header."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],  # a list, pinned: no "alg: none" tricks
            options={"require": ["exp", "sub", "ver"]},
        )
        version = payload["ver"]
        if not isinstance(version, int) or isinstance(version, bool):
            return None
        return int(payload["sub"]), version
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        return None


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep) -> User:
    """The logged-in user, or HTTP 401.

    A token stops working when the account is disabled or deleted, or when the password was changed
    (the user's token_version no longer matches the one inside the token).
    """
    decoded = decode_access_token(token)
    user = session.get(User, decoded[0]) if decoded else None
    if user is None or not user.is_active or decoded is None or user.token_version != decoded[1]:
        raise unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    """Like get_current_user, but answers HTTP 403 "Admin only" for normal users."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


AdminUserDep = Annotated[User, Depends(require_admin)]

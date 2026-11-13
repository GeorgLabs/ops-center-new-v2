"""Registration, login, "who am I" and changing your own password."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app import ratelimit
from app.config import get_settings
from app.db import SessionDep
from app.models import User
from app.schemas import PasswordChange, Token, UserCreate, UserPublic
from app.security import (
    DUMMY_HASH,
    CurrentUser,
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _too_many(wait: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="Too many failed attempts. Try again later.",
        headers={"Retry-After": str(wait)},
    )


@router.post("/register", status_code=201, response_model=UserPublic)
def register(data: UserCreate, session: SessionDep):
    """Create a normal user. Switched off with OPS_ALLOW_REGISTRATION=false (admins then create accounts)."""
    if not get_settings().allow_registration:
        raise HTTPException(status_code=403, detail="Registration is closed. Ask an administrator for an account.")
    username = data.username.lower()  # usernames are not case sensitive
    if session.exec(select(User).where(User.username == username)).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    user = User(username=username, hashed_password=hash_password(data.password))  # never an admin from here
    session.add(user)
    try:
        session.commit()
    except IntegrityError:  # two registrations of the same name at the same moment
        session.rollback()
        raise HTTPException(status_code=409, detail="Username already taken") from None
    session.refresh(user)
    return user


@router.post("/token", response_model=Token)
def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    """The body is a *form* (username, password), the OAuth2 standard - it makes "Authorize" in /docs work."""
    username = form.username.lower()
    # Behind a reverse proxy request.client is the proxy - use the forwarded address there.
    key = (request.client.host if request.client else "?", username)
    wait = ratelimit.blocked_for(key)
    if wait:
        raise _too_many(wait)

    user = session.exec(select(User).where(User.username == username)).first()
    # Always verify something, so a missing user costs the same time as a wrong password.
    password_ok = verify_password(form.password, user.hashed_password if user else DUMMY_HASH)
    if user is None or not password_ok:
        ratelimit.record_failure(key)
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    ratelimit.reset(key)
    if not user.is_active:
        # Only someone who knows the password learns this - no enumeration leak.
        raise HTTPException(status_code=403, detail="This account is disabled. Ask an administrator.")
    return Token(access_token=create_access_token(user.id, user.token_version))  # type: ignore[arg-type]


@router.get("/me", response_model=UserPublic)
def me(user: CurrentUser):
    return user


@router.post("/password", response_model=Token)
def change_password(data: PasswordChange, user: CurrentUser, session: SessionDep):
    """Change your own password. All other sessions are logged out; the answer holds a fresh token for this one."""
    key = ("password", user.id)  # a stolen token must not be able to guess the current password
    wait = ratelimit.blocked_for(key)
    if wait:
        raise _too_many(wait)
    if not verify_password(data.current_password, user.hashed_password):
        ratelimit.record_failure(key)
        raise HTTPException(status_code=400, detail="Current password is wrong")
    ratelimit.reset(key)
    if data.new_password == data.current_password:
        raise HTTPException(status_code=400, detail="The new password must be different from the current one")
    user.hashed_password = hash_password(data.new_password)
    user.token_version += 1  # invalidates every token issued so far
    session.add(user)
    session.commit()
    session.refresh(user)
    return Token(access_token=create_access_token(user.id, user.token_version))  # type: ignore[arg-type]

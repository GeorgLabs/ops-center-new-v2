"""First start: make sure the administrator from .env exists.

The rule is simple and deliberately conservative:
  * OPS_ADMIN_USERNAME / OPS_ADMIN_PASSWORD not set  -> do nothing.
  * a user with that name already exists              -> do nothing (never touch an existing account).
  * otherwise                                         -> create it as an active administrator.
So the password in .env is only a *starting* password. Later changes there have no effect.
"""

import logging
from typing import Literal

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.models import User
from app.security import hash_password

log = logging.getLogger("uvicorn.error")  # shows up in the server's console

Result = Literal["created", "exists", "skipped"]


def ensure_admin(engine: Engine, settings: Settings | None = None) -> Result:
    settings = settings or get_settings()
    if settings.admin_username is None or settings.admin_password is None:
        log.info("No OPS_ADMIN_USERNAME/OPS_ADMIN_PASSWORD set: not creating an admin account.")
        return "skipped"

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == settings.admin_username)).first()
        if existing is not None:
            if not existing.is_admin:
                log.warning(
                    "User '%s' exists but is not an administrator. Leaving it as it is "
                    "(promote it in the admin panel, or pick another OPS_ADMIN_USERNAME).",
                    existing.username,
                )
            return "exists"

        session.add(
            User(
                username=settings.admin_username,
                hashed_password=hash_password(settings.admin_password.get_secret_value()),
                is_admin=True,
            )
        )
        try:
            session.commit()
        except IntegrityError:  # another process created it in the same moment
            session.rollback()
            return "exists"
    log.info("Created administrator '%s' from the OPS_ADMIN_* settings.", settings.admin_username)
    return "created"

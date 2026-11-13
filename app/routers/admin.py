"""Admin area: manage users and look at every host. Every endpoint needs an administrator.

Safety rules (an admin can lock themselves out otherwise):
  * you cannot change your own role/status, reset your own password here, or delete yourself
    -> there is always at least one working administrator: you.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from app.config import get_settings
from app.db import SessionDep
from app.models import Host, Metric, User, utcnow
from app.routers.hosts import to_public
from app.schemas import (
    AdminHost,
    AdminPasswordReset,
    AdminStats,
    AdminUser,
    AdminUserCreate,
    AdminUserUpdate,
)
from app.security import AdminUserDep, hash_password, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _get_user(session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _not_yourself(admin: User, user: User, what: str) -> None:
    if admin.id == user.id:
        raise HTTPException(status_code=400, detail=f"You cannot {what} your own account")


def _admin_user(session, user: User) -> AdminUser:
    count = session.exec(select(func.count()).select_from(Host).where(Host.owner_id == user.id)).one()
    return AdminUser(
        id=user.id,  # type: ignore[arg-type]
        username=user.username,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        host_count=count,
    )


@router.get("/stats", response_model=AdminStats)
def stats(session: SessionDep):
    def count(stmt) -> int:
        return session.exec(stmt).one()

    window_start = utcnow() - timedelta(seconds=get_settings().online_window_seconds)
    online = count(
        select(func.count(func.distinct(Metric.host_id))).where(Metric.ts >= window_start)
    )
    return AdminStats(
        users=count(select(func.count()).select_from(User)),
        admins=count(select(func.count()).select_from(User).where(col(User.is_admin).is_(True))),
        disabled_users=count(select(func.count()).select_from(User).where(col(User.is_active).is_(False))),
        hosts=count(select(func.count()).select_from(Host)),
        hosts_online=online,
        metrics=count(select(func.count()).select_from(Metric)),
    )


# ---------------------------------------------------------------- users
@router.get("/users", response_model=list[AdminUser])
def list_users(
    session: SessionDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    q: str | None = Query(None, max_length=32),
):
    stmt = select(User)
    if q:
        stmt = stmt.where(col(User.username).icontains(q, autoescape=True))
    users = session.exec(stmt.order_by(col(User.id)).offset(skip).limit(limit)).all()
    return [_admin_user(session, u) for u in users]


@router.post("/users", status_code=201, response_model=AdminUser)
def create_user(data: AdminUserCreate, session: SessionDep):
    username = data.username.lower()
    if session.exec(select(User).where(User.username == username)).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    user = User(username=username, hashed_password=hash_password(data.password), is_admin=data.is_admin)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Username already taken") from None
    session.refresh(user)
    return _admin_user(session, user)


@router.get("/users/{user_id}", response_model=AdminUser)
def get_user(user_id: int, session: SessionDep):
    return _admin_user(session, _get_user(session, user_id))


@router.patch("/users/{user_id}", response_model=AdminUser)
def update_user(user_id: int, data: AdminUserUpdate, session: SessionDep, admin: AdminUserDep):
    user = _get_user(session, user_id)
    _not_yourself(admin, user, "change the role or status of")
    changes = data.model_dump(exclude_unset=True)
    if "is_admin" in changes and changes["is_admin"] is not None:
        user.is_admin = changes["is_admin"]
    if "is_active" in changes and changes["is_active"] is not None:
        if user.is_active and not changes["is_active"]:
            user.token_version += 1  # kick out anyone currently logged in as this user
        user.is_active = changes["is_active"]
    session.add(user)
    session.commit()
    session.refresh(user)
    return _admin_user(session, user)


@router.post("/users/{user_id}/password", status_code=204)
def reset_password(user_id: int, data: AdminPasswordReset, session: SessionDep, admin: AdminUserDep):
    """Set a new password for someone who forgot theirs. Their old sessions end immediately."""
    user = _get_user(session, user_id)
    _not_yourself(admin, user, "reset the password of (use 'change password')")
    user.hashed_password = hash_password(data.new_password)
    user.token_version += 1
    session.add(user)
    session.commit()
    return Response(status_code=204)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, session: SessionDep, admin: AdminUserDep):
    """Deletes the user together with their hosts and all measurements."""
    user = _get_user(session, user_id)
    _not_yourself(admin, user, "delete")
    host_ids = select(Host.id).where(Host.owner_id == user.id)
    # Plain SQL deletes: a busy host has hundreds of thousands of measurements, we must not load them.
    session.exec(delete(Metric).where(col(Metric.host_id).in_(host_ids)))  # type: ignore[call-overload]
    session.exec(delete(Host).where(col(Host.owner_id) == user.id))  # type: ignore[call-overload]
    session.exec(delete(User).where(col(User.id) == user.id))  # type: ignore[call-overload]
    session.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- hosts (everybody's)
@router.get("/hosts", response_model=list[AdminHost])
def list_all_hosts(
    session: SessionDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    q: str | None = Query(None, max_length=50),
):
    stmt = select(Host, User.username).join(User, col(Host.owner_id) == col(User.id), isouter=True)
    if q:
        stmt = stmt.where(col(Host.name).icontains(q, autoescape=True))
    rows = session.exec(stmt.order_by(col(Host.id)).offset(skip).limit(limit)).all()
    return [
        AdminHost(**to_public(host, session).model_dump(), owner_id=host.owner_id, owner_username=owner)
        for host, owner in rows
    ]


@router.delete("/hosts/{host_id}", status_code=204)
def delete_any_host(host_id: int, session: SessionDep):
    host = session.get(Host, host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")
    session.delete(host)  # the database deletes its measurements (ON DELETE CASCADE)
    session.commit()
    return Response(status_code=204)

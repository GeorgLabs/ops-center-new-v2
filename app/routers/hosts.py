"""Hosts and their metrics (SQLModel). Every query is scoped to the logged-in owner.

Pattern for every endpoint: take a `session: SessionDep`, query with `select(...)`,
return a Pydantic schema (never the table object itself).
"""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, Response
from sqlmodel import Session, col, select

from app.apikeys import hash_api_key, new_api_key
from app.config import get_settings
from app.db import SessionDep
from app.models import Host, Metric, utcnow
from app.schemas import HostCreate, HostCreated, HostPublic, MetricPublic
from app.security import CurrentUser

router = APIRouter(prefix="/api/hosts", tags=["hosts"])


def to_public(host: Host, session: Session) -> HostPublic:
    """Host + its newest metric -> what the dashboard shows (N+1 queries: fine at this size)."""
    latest = session.exec(
        select(Metric)
        .where(Metric.host_id == host.id)
        .order_by(col(Metric.ts).desc(), col(Metric.id).desc())
        .limit(1)
    ).first()
    if latest is None:
        status = "unknown"
    else:
        window = timedelta(seconds=get_settings().online_window_seconds)
        status = "online" if utcnow() - latest.ts <= window else "offline"
    return HostPublic(
        id=host.id,  # type: ignore[arg-type]
        name=host.name,
        description=host.description,
        created_at=host.created_at,
        status=status,
        last_seen=latest.ts if latest else None,
        cpu_percent=latest.cpu_percent if latest else None,
        memory_percent=latest.memory_percent if latest else None,
        disk_percent=latest.disk_percent if latest else None,
    )


def _get_own_host(session: Session, host_id: int, user) -> Host:
    """404 - not 403 - for hosts that are not yours: do not even confirm that they exist."""
    host = session.exec(
        select(Host).where(Host.id == host_id, Host.owner_id == user.id)
    ).first()
    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")
    return host


@router.post("", status_code=201, response_model=HostCreated)
def create_host(data: HostCreate, session: SessionDep, user: CurrentUser):
    key = new_api_key()
    host = Host(
        name=data.name,
        description=data.description,
        api_key_hash=hash_api_key(key),  # we store the hash; the key itself is shown once
        owner_id=user.id,
    )
    session.add(host)
    session.commit()
    session.refresh(host)
    return HostCreated(
        id=host.id,  # type: ignore[arg-type]
        name=host.name,
        description=host.description,
        created_at=host.created_at,
        api_key=key,
    )


@router.get("", response_model=list[HostPublic])
def list_hosts(
    session: SessionDep,
    user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    q: str | None = Query(None, max_length=50),
):
    stmt = select(Host).where(Host.owner_id == user.id)
    if q:
        # autoescape: a "%" typed by the user is a plain character, not a LIKE wildcard
        stmt = stmt.where(col(Host.name).icontains(q, autoescape=True))
    hosts = session.exec(stmt.order_by(col(Host.id)).offset(skip).limit(limit)).all()
    return [to_public(h, session) for h in hosts]


@router.get("/{host_id}", response_model=HostPublic)
def get_host(host_id: int, session: SessionDep, user: CurrentUser):
    return to_public(_get_own_host(session, host_id, user), session)


@router.get("/{host_id}/metrics", response_model=list[MetricPublic])
def host_metrics(
    host_id: int,
    session: SessionDep,
    user: CurrentUser,
    minutes: int = Query(60, ge=1, le=1440),
    limit: int = Query(500, ge=1, le=5000),
):
    host = _get_own_host(session, host_id, user)
    since = utcnow() - timedelta(minutes=minutes)
    rows = session.exec(
        select(Metric)
        .where(Metric.host_id == host.id, Metric.ts >= since)
        .order_by(col(Metric.ts).desc(), col(Metric.id).desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))  # newest `limit` rows, oldest first (nice for charts)


@router.delete("/{host_id}", status_code=204)
def delete_host(host_id: int, session: SessionDep, user: CurrentUser):
    host = _get_own_host(session, host_id, user)
    session.delete(host)  # its metrics go with it (cascade)
    session.commit()
    return Response(status_code=204)

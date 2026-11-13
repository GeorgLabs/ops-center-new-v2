"""Where the agents report in. Machines authenticate with an API key, not a login."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlmodel import select

from app.apikeys import hash_api_key
from app.db import SessionDep
from app.models import Host, Metric, User
from app.schemas import MetricIn, MetricPublic

router = APIRouter(prefix="/api", tags=["agents"])

# `auto_error=False` -> we raise the 401 ourselves, so a missing key and a wrong key look the same.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_agent_host(key: Annotated[str | None, Depends(api_key_header)], session: SessionDep) -> Host:
    """Which host does this API key belong to? Missing/unknown key (or a disabled owner) -> 401."""
    host = None
    if key:
        host = session.exec(select(Host).where(Host.api_key_hash == hash_api_key(key))).first()
    owner = session.get(User, host.owner_id) if host and host.owner_id else None
    if host is None or (owner is not None and not owner.is_active):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return host


@router.post("/ingest", status_code=201, response_model=MetricPublic)
def ingest(
    data: MetricIn,
    host: Annotated[Host, Depends(get_agent_host)],
    session: SessionDep,
):
    """Store one measurement for the host that owns the key. The body never says WHICH host - the key decides."""
    metric = Metric(host_id=host.id, **data.model_dump())  # type: ignore[arg-type]
    session.add(metric)
    session.commit()
    session.refresh(metric)
    return metric

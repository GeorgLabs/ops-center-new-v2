"""System info (psutil) and the public settings the login screen needs."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app import collectors
from app.config import get_settings
from app.schemas import PublicConfig
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["system"])


class SystemInfo(BaseModel):
    hostname: str
    os: str
    cpu_count: int = Field(ge=1)
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)
    uptime_seconds: int = Field(ge=0)


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/config", response_model=PublicConfig)
def public_config() -> PublicConfig:
    settings = get_settings()
    return PublicConfig(registration_open=settings.allow_registration, docs_enabled=settings.dev)


@router.get("/system", response_model=SystemInfo, dependencies=[Depends(get_current_user)])
def system() -> dict:
    return collectors.system_info()


@router.get(
    "/system/processes",
    response_model=list[ProcessInfo],
    dependencies=[Depends(get_current_user)],
)
def processes(
    limit: int = Query(5, ge=1, le=25),
    sort_by: Literal["cpu", "memory", "name"] = "cpu",
) -> list[dict]:
    procs = collectors.list_processes()
    if sort_by == "name":
        procs.sort(key=lambda p: p["name"].lower())
    else:
        procs.sort(key=lambda p: p[f"{sort_by}_percent"], reverse=True)
    return procs[:limit]

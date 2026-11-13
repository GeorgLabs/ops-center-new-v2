"""What goes over the wire: request and response bodies (Pydantic).

Pydantic validates everything that comes in *before* your endpoint code runs,
so inside an endpoint you can trust the data.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HostStatus = Literal["online", "offline", "unknown"]


# ---------------------------------------------------------------- hosts
class HostCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=200)


class HostPublic(BaseModel):
    """A host as the dashboard sees it. NEVER contains the API key."""

    id: int
    name: str
    description: str
    created_at: datetime
    status: HostStatus
    last_seen: datetime | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float | None = None


class HostCreated(BaseModel):
    """Answer to POST /api/hosts - the only time the API key is ever shown."""

    id: int
    name: str
    description: str
    created_at: datetime
    api_key: str


# ---------------------------------------------------------------- metrics
class MetricIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)


class MetricPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float


# ---------------------------------------------------------------- users
USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"


class UserCreate(BaseModel):
    """Self-registration. Note what is NOT here: nobody can choose their own role."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=128)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - the OAuth2 token *type*, not a secret


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PublicConfig(BaseModel):
    """What the login screen needs to know before anyone is logged in."""

    registration_open: bool
    docs_enabled: bool = False


# ---------------------------------------------------------------- admin
class AdminUser(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    host_count: int = 0


class AdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=128)
    is_admin: bool = False


class AdminUserUpdate(BaseModel):
    """Only the fields that are sent are changed."""

    model_config = ConfigDict(extra="forbid")

    is_admin: bool | None = None
    is_active: bool | None = None


class AdminPasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=8, max_length=128)


class AdminHost(HostPublic):
    owner_id: int | None = None
    owner_username: str | None = None


class AdminStats(BaseModel):
    users: int
    admins: int
    disabled_users: int
    hosts: int
    hosts_online: int
    metrics: int

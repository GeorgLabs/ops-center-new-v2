"""Database tables (SQLModel). One class = one table.

These are *table* models: they describe how data is stored. What goes over the wire
(request / response bodies) is described by separate Pydantic models in schemas.py -
never return a table model directly from an endpoint, it may contain secrets.
"""

from datetime import UTC, datetime

from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    """Current time in UTC with the time zone attached (JSON ends in 'Z', browsers show the right clock)."""
    return datetime.now(UTC)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(max_length=32, unique=True, index=True)
    hashed_password: str  # an Argon2 hash - the real password is never stored
    is_admin: bool = False
    is_active: bool = True  # False = account disabled: cannot log in, existing tokens stop working
    # Part of every login token. Changing a password (or disabling an account) raises it,
    # which instantly invalidates all tokens issued before.
    token_version: int = 0
    created_at: datetime = Field(default_factory=utcnow)

    hosts: list["Host"] = Relationship(back_populates="owner")


class Host(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=50, index=True)
    description: str = Field(default="", max_length=200)
    api_key_hash: str = Field(unique=True, index=True)  # sha256 of the agent's key
    owner_id: int | None = Field(default=None, foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)

    owner: User | None = Relationship(back_populates="hosts")
    # The database deletes the measurements (ON DELETE CASCADE); Python must not load them all first.
    metrics: list["Metric"] = Relationship(back_populates="host", cascade_delete=True, passive_deletes=True)


class Metric(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    host_id: int = Field(foreign_key="host.id", ondelete="CASCADE", index=True)
    ts: datetime = Field(default_factory=utcnow, index=True)
    cpu_percent: float
    memory_percent: float
    disk_percent: float

    host: Host | None = Relationship(back_populates="metrics")

"""Settings. They come from environment variables (prefix OPS_) or from the .env file.

Rule number one of secure software: secrets never live in the source code.
`setup.bat` / `setup.sh` (or `python scripts/init_env.py`) creates a .env with fresh random secrets.
"""

import re
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPS_", env_file=ROOT / ".env", extra="ignore")

    secret_key: SecretStr  # signs the login tokens - required, no default on purpose
    database_url: str = f"sqlite:///{(ROOT / 'opscenter.db').as_posix()}"
    dev: bool = False  # serves /docs and /openapi.json - off unless asked for
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    online_window_seconds: int = 60  # a host counts as "online" if it reported this recently
    allow_registration: bool = True  # False = only admins can create accounts

    # The first administrator. Created at startup, but ONLY if no user with that name exists yet:
    # changing the password here later does nothing (use "change password" in the app).
    admin_username: str | None = None
    admin_password: SecretStr | None = None

    @field_validator("secret_key")
    @classmethod
    def _key_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("OPS_SECRET_KEY must be at least 32 characters long")
        return value

    @field_validator("admin_username", "admin_password", mode="before")
    @classmethod
    def _empty_means_unset(cls, value):
        # docker compose passes unset variables as "" - treat that as "not configured"
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("admin_username")
    @classmethod
    def _admin_name_ok(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()  # usernames are not case sensitive
        if not USERNAME_RE.match(value):
            raise ValueError("OPS_ADMIN_USERNAME must be 3-32 characters: letters, digits, _ . -")
        return value

    @field_validator("admin_password")
    @classmethod
    def _admin_password_strong_enough(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not 12 <= len(value.get_secret_value()) <= 128:
            raise ValueError("OPS_ADMIN_PASSWORD must be 12-128 characters long")
        return value

    @model_validator(mode="after")
    def _admin_is_all_or_nothing(self) -> "Settings":
        if (self.admin_username is None) != (self.admin_password is None):
            raise ValueError("set both OPS_ADMIN_USERNAME and OPS_ADMIN_PASSWORD, or neither")
        return self


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "settings"
        raise SystemExit(
            "\nOps Center is not configured correctly.\n"
            "Run setup.bat (Windows) or ./setup.sh to create your .env file, or set the OPS_* variables.\n"
            f"Problem: {where}: {first['msg']}\n"
        ) from exc

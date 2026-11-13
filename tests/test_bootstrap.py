"""The administrator from .env: created once, only if missing, never overwritten."""

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from app.bootstrap import ensure_admin
from app.config import Settings
from app.models import User
from app.security import verify_password

KEY = "k" * 40


def cfg(**kw) -> Settings:
    return Settings(secret_key=KEY, _env_file=None, **kw)


def users(engine) -> list[User]:
    with Session(engine) as db:
        return list(db.exec(select(User)).all())


def test_creates_the_admin_when_missing(engine):
    assert ensure_admin(engine, cfg(admin_username="Boss", admin_password="long-enough-pass")) == "created"
    (boss,) = users(engine)
    assert boss.username == "boss" and boss.is_admin and boss.is_active
    assert boss.hashed_password.startswith("$argon2") and verify_password("long-enough-pass", boss.hashed_password)


def test_does_nothing_when_not_configured(engine):
    assert ensure_admin(engine, cfg()) == "skipped"
    assert users(engine) == []


def test_never_touches_an_existing_account(engine):
    settings = cfg(admin_username="boss", admin_password="first-password-123")
    ensure_admin(engine, settings)
    with Session(engine) as db:  # the admin changed the password in the app meanwhile
        boss = db.exec(select(User)).one()
        boss.hashed_password = "changed-in-the-app"
        boss.token_version = 3
        db.add(boss)
        db.commit()
    assert ensure_admin(engine, cfg(admin_username="boss", admin_password="different-in-env-1")) == "exists"
    (boss,) = users(engine)
    assert boss.hashed_password == "changed-in-the-app" and boss.token_version == 3


def test_a_deleted_admin_comes_back_on_the_next_start(engine):
    settings = cfg(admin_username="boss", admin_password="long-enough-pass")
    ensure_admin(engine, settings)
    with Session(engine) as db:
        db.delete(db.exec(select(User)).one())
        db.commit()
    assert ensure_admin(engine, settings) == "created"


def test_does_not_promote_a_normal_user_with_the_same_name(engine, caplog):
    with Session(engine) as db:
        db.add(User(username="boss", hashed_password="x"))
        db.commit()
    with caplog.at_level("WARNING"):
        assert ensure_admin(engine, cfg(admin_username="boss", admin_password="long-enough-pass")) == "exists"
    assert users(engine)[0].is_admin is False
    assert "not an administrator" in caplog.text


@pytest.mark.parametrize(
    "kw",
    [
        {"admin_username": "boss"},  # password missing
        {"admin_password": "long-enough-pass"},  # name missing
        {"admin_username": "boss", "admin_password": "short"},
        {"admin_username": "x y", "admin_password": "long-enough-pass"},
    ],
)
def test_bad_admin_settings_are_refused_at_startup(kw):
    with pytest.raises(ValidationError):
        cfg(**kw)


def test_empty_values_count_as_unset():
    s = cfg(admin_username="", admin_password="")
    assert s.admin_username is None and s.admin_password is None


def test_the_admin_can_log_in_through_the_real_startup(tmp_path, monkeypatch):
    """Whole path: migrations -> bootstrap -> login, on a real SQLite file."""
    from fastapi.testclient import TestClient

    from app import config, db, main

    monkeypatch.setenv("OPS_DATABASE_URL", f"sqlite:///{(tmp_path / 't.db').as_posix()}")
    monkeypatch.setenv("OPS_ADMIN_USERNAME", "root")
    monkeypatch.setenv("OPS_ADMIN_PASSWORD", "start-password-1")
    config.get_settings.cache_clear()
    db.get_engine.cache_clear()
    try:
        app = main.create_app(dev=False)
        with TestClient(app) as c:  # `with` runs the lifespan = startup
            res = c.post("/api/auth/token", data={"username": "root", "password": "start-password-1"})
            assert res.status_code == 200
            tok = {"Authorization": f"Bearer {res.json()['access_token']}"}
            assert c.get("/api/admin/stats", headers=tok).status_code == 200
        with TestClient(app) as c:  # second start: still exactly one root, password unchanged
            assert c.post("/api/auth/token", data={"username": "root", "password": "start-password-1"}).status_code == 200
    finally:
        config.get_settings.cache_clear()
        db.get_engine.cache_clear()

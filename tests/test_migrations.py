"""Upgrading an existing database (made by the first version of the app) must keep its users."""

import sqlite3

from alembic import command
from alembic.config import Config

from app import config, db
from app.config import ROOT


def alembic_cfg() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def test_0001_to_0002_keeps_users_and_fills_new_columns(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    monkeypatch.setenv("OPS_DATABASE_URL", f"sqlite:///{path.as_posix()}")
    config.get_settings.cache_clear()
    db.get_engine.cache_clear()
    try:
        command.upgrade(alembic_cfg(), "0001")
        with sqlite3.connect(path) as con:
            con.execute(
                "INSERT INTO user (username, hashed_password, is_admin, created_at) VALUES ('old', 'x', 1, '2026-01-01 00:00:00.000000')"
            )
        command.upgrade(alembic_cfg(), "head")
        with sqlite3.connect(path) as con:
            row = con.execute("SELECT username, is_admin, is_active, token_version FROM user").fetchone()
        assert row == ("old", 1, 1, 0)  # still an active admin, version 0
        command.downgrade(alembic_cfg(), "0001")
        with sqlite3.connect(path) as con:
            columns = [c[1] for c in con.execute("PRAGMA table_info(user)")]
        assert "is_active" not in columns and "token_version" not in columns
    finally:
        config.get_settings.cache_clear()
        db.get_engine.cache_clear()

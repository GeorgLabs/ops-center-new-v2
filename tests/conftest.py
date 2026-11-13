"""Shared test setup: every test gets a brand-new, empty in-memory database."""

import os

# Tests must not depend on (or touch) your real .env: set what the app needs, switch the rest off.
os.environ["OPS_SECRET_KEY"] = "test-secret-key-test-secret-key-0123456789"
os.environ["OPS_ADMIN_USERNAME"] = ""
os.environ["OPS_ADMIN_PASSWORD"] = ""
os.environ["OPS_ALLOW_REGISTRATION"] = "true"
os.environ["OPS_DEV"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app import ratelimit  # noqa: E402
from app.db import get_session, make_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    ratelimit._failures.clear()
    yield
    ratelimit._failures.clear()


@pytest.fixture
def engine():
    engine = make_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def app(engine):
    app = create_app(dev=False, migrate=False)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def make_user(engine):
    """make_user("alice", admin=True) -> the user exists in the database (password: PASSWORD)."""

    def _make(username: str, *, admin: bool = False, active: bool = True) -> int:
        with Session(engine) as db:
            user = User(username=username, hashed_password=hash_password(PASSWORD), is_admin=admin, is_active=active)
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.id

    return _make


@pytest.fixture
def login(app):
    """login("alice") -> a fresh client that is signed in as alice."""

    def _login(username: str, password: str = PASSWORD) -> TestClient:
        c = TestClient(app)
        res = c.post("/api/auth/token", data={"username": username, "password": password})
        assert res.status_code == 200, res.text
        c.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
        return c

    return _login


@pytest.fixture
def auth_client(client):
    """A client that is registered and logged in."""
    body = {"username": "tester", "password": PASSWORD}
    client.post("/api/auth/register", json=body)
    token = client.post("/api/auth/token", data=body).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def admin_client(make_user, login):
    make_user("root", admin=True)
    return login("root")

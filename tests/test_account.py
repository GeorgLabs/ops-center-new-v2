"""Registration switch, disabled accounts, changing your own password."""

import jwt

from app.config import get_settings
from tests.conftest import PASSWORD

NEW = "an-even-better-password"


def test_register_never_makes_an_admin(client):
    res = client.post("/api/auth/register", json={"username": "mallory", "password": PASSWORD, "is_admin": True})
    assert res.status_code == 422  # unknown field is refused
    res = client.post("/api/auth/register", json={"username": "mallory", "password": PASSWORD})
    assert res.status_code == 201 and res.json()["is_admin"] is False


def test_registration_can_be_closed(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_registration", False)
    assert client.get("/api/config").json()["registration_open"] is False
    assert client.post("/api/auth/register", json={"username": "newbie", "password": PASSWORD}).status_code == 403


def test_change_password(auth_client, client):
    res = auth_client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW})
    assert res.status_code == 200
    # old password is dead, new one works
    assert client.post("/api/auth/token", data={"username": "tester", "password": PASSWORD}).status_code == 401
    assert client.post("/api/auth/token", data={"username": "tester", "password": NEW}).status_code == 200
    # the token in the answer keeps this session alive; the old token is dead
    fresh = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=fresh).status_code == 200
    assert auth_client.get("/api/auth/me").status_code == 401  # still carries the old token


def test_change_password_needs_the_current_one(auth_client):
    res = auth_client.post("/api/auth/password", json={"current_password": "nope-nope-nope", "new_password": NEW})
    assert res.status_code == 400
    assert auth_client.get("/api/auth/me").status_code == 200  # nothing happened


def test_change_password_rules(auth_client):
    same = auth_client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert same.status_code == 400
    short = auth_client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"})
    assert short.status_code == 422


def test_change_password_needs_login_and_is_rate_limited(client, auth_client):
    anon = client.__class__(client.app)
    assert anon.post("/api/auth/password", json={"current_password": "x", "new_password": NEW * 2}).status_code == 401
    codes = [
        auth_client.post("/api/auth/password", json={"current_password": f"wrong-{i}", "new_password": NEW}).status_code
        for i in range(7)
    ]
    assert codes[:5] == [400] * 5 and 429 in codes
    # even the right password is refused while locked
    assert auth_client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW}).status_code == 429


def test_token_carries_a_version_and_old_style_tokens_are_refused(client, make_user):
    make_user("erin")
    token = client.post("/api/auth/token", data={"username": "erin", "password": PASSWORD}).json()["access_token"]
    claims = jwt.decode(token, options={"verify_signature": False})
    assert {"sub", "ver", "iat", "exp"} <= claims.keys() and claims["ver"] == 0
    secret = get_settings().secret_key.get_secret_value()
    no_version = jwt.encode({"sub": "1", "exp": claims["exp"]}, secret, algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {no_version}"}).status_code == 401


def test_disabled_account(client, make_user, login):
    make_user("frank")
    c = login("frank")
    make_user("root", admin=True)
    admin = login("root")
    uid = c.get("/api/auth/me").json()["id"]
    assert admin.patch(f"/api/admin/users/{uid}", json={"is_active": False}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401  # the running session ends at once
    wrong = client.post("/api/auth/token", data={"username": "frank", "password": "wrong-wrong-1"})
    right = client.post("/api/auth/token", data={"username": "frank", "password": PASSWORD})
    assert wrong.status_code == 401
    assert right.status_code == 403  # only someone who knows the password learns the account is disabled
    assert admin.patch(f"/api/admin/users/{uid}", json={"is_active": True}).status_code == 200
    assert client.post("/api/auth/token", data={"username": "frank", "password": PASSWORD}).status_code == 200

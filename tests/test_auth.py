import jwt


def test_password_is_hashed(client, engine):
    from sqlmodel import Session, select

    from app.models import User

    client.post("/api/auth/register", json={"username": "carol", "password": "correct-horse-battery"})
    with Session(engine) as db:
        user = db.exec(select(User)).one()
    assert user.hashed_password.startswith("$argon2")


def test_me_needs_a_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    forged = jwt.encode({"sub": "1", "exp": 4102444800}, "x" * 40, algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_login_gets_locked_after_five_failures(client):
    client.post("/api/auth/register", json={"username": "dave", "password": "correct-horse-battery"})
    codes = [
        client.post("/api/auth/token", data={"username": "dave", "password": f"bad-{i}"}).status_code
        for i in range(7)
    ]
    assert codes[:5] == [401] * 5
    assert 429 in codes

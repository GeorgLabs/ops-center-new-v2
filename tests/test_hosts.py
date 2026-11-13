def make_host(client, name="web-1"):
    resp = client.post("/api/hosts", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def test_create_returns_key_once(auth_client):
    host = make_host(auth_client)
    assert host["api_key"].startswith("ops_")
    listed = auth_client.get("/api/hosts").json()
    assert listed[0]["name"] == "web-1"
    assert "api_key" not in listed[0]


def test_ingest_makes_host_online(auth_client):
    host = make_host(auth_client)
    body = {"cpu_percent": 5, "memory_percent": 6, "disk_percent": 7}
    resp = auth_client.post("/api/ingest", json=body, headers={"X-API-Key": host["api_key"]})
    assert resp.status_code == 201
    assert auth_client.get(f"/api/hosts/{host['id']}").json()["status"] == "online"


def test_other_users_cannot_see_my_host(client, auth_client):
    host = make_host(auth_client)
    client.headers.pop("Authorization")
    body = {"username": "mallory", "password": "correct-horse-battery"}
    client.post("/api/auth/register", json=body)
    token = client.post("/api/auth/token", data=body).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    assert client.get(f"/api/hosts/{host['id']}").status_code == 404
    assert client.delete(f"/api/hosts/{host['id']}").status_code == 404

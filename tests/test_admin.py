"""The admin API: who may use it, what it does, and the rules that stop admins from locking themselves out."""

import pytest

from tests.conftest import PASSWORD


def make_host(c, name="web-1"):
    return c.post("/api/hosts", json={"name": name}).json()


def test_admin_area_is_closed_to_everybody_else(client, auth_client):
    urls = ["/api/admin/stats", "/api/admin/users", "/api/admin/hosts"]
    for url in urls:
        assert auth_client.get(url).status_code == 403, url  # logged in, but not an admin
    anon = client.__class__(client.app)
    for url in urls:
        assert anon.get(url).status_code == 401, url
    assert auth_client.post("/api/admin/users", json={"username": "x" * 5, "password": PASSWORD}).status_code == 403
    assert auth_client.patch("/api/admin/users/1", json={"is_admin": True}).status_code == 403
    assert auth_client.delete("/api/admin/users/1").status_code == 403
    assert auth_client.post("/api/admin/users/1/password", json={"new_password": PASSWORD}).status_code == 403


def test_list_users_with_host_counts_and_search(admin_client, make_user, login):
    make_user("alice")
    alice = login("alice")
    make_host(alice, "a1")
    make_host(alice, "a2")
    users = admin_client.get("/api/admin/users").json()
    by_name = {u["username"]: u for u in users}
    assert by_name["alice"]["host_count"] == 2 and by_name["root"]["is_admin"] is True
    assert "hashed_password" not in users[0]
    assert [u["username"] for u in admin_client.get("/api/admin/users?q=ali").json()] == ["alice"]
    assert [u["username"] for u in admin_client.get("/api/admin/users?q=%25").json()] == []  # % is not a wildcard


def test_create_user(admin_client, client):
    res = admin_client.post("/api/admin/users", json={"username": "Zoe", "password": PASSWORD, "is_admin": True})
    assert res.status_code == 201 and res.json()["username"] == "zoe" and res.json()["is_admin"] is True
    assert admin_client.post("/api/admin/users", json={"username": "zoe", "password": PASSWORD}).status_code == 409
    assert client.post("/api/auth/token", data={"username": "zoe", "password": PASSWORD}).status_code == 200
    assert admin_client.post("/api/admin/users", json={"username": "ab", "password": PASSWORD}).status_code == 422


def test_promote_and_demote(admin_client, make_user, login):
    uid = make_user("bob")
    bob = login("bob")
    assert bob.get("/api/admin/users").status_code == 403
    assert admin_client.patch(f"/api/admin/users/{uid}", json={"is_admin": True}).json()["is_admin"] is True
    assert bob.get("/api/admin/users").status_code == 200
    assert admin_client.patch(f"/api/admin/users/{uid}", json={"is_admin": False}).json()["is_admin"] is False
    assert bob.get("/api/admin/users").status_code == 403


def test_patch_only_known_fields(admin_client, make_user):
    uid = make_user("bob")
    assert admin_client.patch(f"/api/admin/users/{uid}", json={"username": "evil"}).status_code == 422
    assert admin_client.patch(f"/api/admin/users/{uid}", json={"hashed_password": "x"}).status_code == 422
    assert admin_client.patch(f"/api/admin/users/{uid}", json={}).status_code == 200  # nothing to change is fine


def test_admins_cannot_lock_themselves_out(admin_client):
    me = admin_client.get("/api/auth/me").json()["id"]
    assert admin_client.patch(f"/api/admin/users/{me}", json={"is_admin": False}).status_code == 400
    assert admin_client.patch(f"/api/admin/users/{me}", json={"is_active": False}).status_code == 400
    assert admin_client.delete(f"/api/admin/users/{me}").status_code == 400
    assert admin_client.post(f"/api/admin/users/{me}/password", json={"new_password": PASSWORD}).status_code == 400
    assert admin_client.get("/api/auth/me").json()["is_admin"] is True


def test_reset_password(admin_client, make_user, login, client):
    uid = make_user("carl")
    carl = login("carl")
    assert admin_client.post(f"/api/admin/users/{uid}/password", json={"new_password": "brand-new-pass"}).status_code == 204
    assert carl.get("/api/auth/me").status_code == 401  # old session is over
    assert client.post("/api/auth/token", data={"username": "carl", "password": PASSWORD}).status_code == 401
    assert client.post("/api/auth/token", data={"username": "carl", "password": "brand-new-pass"}).status_code == 200
    assert admin_client.post(f"/api/admin/users/{uid}/password", json={"new_password": "short"}).status_code == 422


def test_unknown_user_is_404(admin_client):
    assert admin_client.get("/api/admin/users/999").status_code == 404
    assert admin_client.patch("/api/admin/users/999", json={"is_admin": True}).status_code == 404
    assert admin_client.delete("/api/admin/users/999").status_code == 404
    assert admin_client.post("/api/admin/users/999/password", json={"new_password": PASSWORD}).status_code == 404


def test_delete_user_removes_their_hosts_and_measurements(admin_client, make_user, login, engine):
    from sqlmodel import Session, func, select

    from app.models import Host, Metric

    make_user("dora")
    make_user("eve")
    dora, eve = login("dora"), login("eve")
    created = make_host(dora)
    make_host(eve, "keep-me")
    for _ in range(3):
        r = dora.post("/api/ingest", json={"cpu_percent": 1, "memory_percent": 2, "disk_percent": 3}, headers={"X-API-Key": created["api_key"]})
        assert r.status_code == 201
    dora_id = dora.get("/api/auth/me").json()["id"]
    assert admin_client.delete(f"/api/admin/users/{dora_id}").status_code == 204
    with Session(engine) as db:
        assert db.exec(select(func.count()).select_from(Metric)).one() == 0
        assert [h.name for h in db.exec(select(Host)).all()] == ["keep-me"]
    assert dora.get("/api/auth/me").status_code == 401
    assert eve.get("/api/hosts").status_code == 200


def test_all_hosts_and_delete_any_host(admin_client, make_user, login):
    make_user("gus")
    gus = login("gus")
    h = make_host(gus, "gus-box")
    hosts = admin_client.get("/api/admin/hosts").json()
    assert hosts[0]["name"] == "gus-box" and hosts[0]["owner_username"] == "gus" and "api_key" not in hosts[0]
    assert admin_client.get("/api/admin/hosts?q=nothing").json() == []
    assert admin_client.delete(f"/api/admin/hosts/{h['id']}").status_code == 204
    assert admin_client.delete(f"/api/admin/hosts/{h['id']}").status_code == 404
    assert gus.get("/api/hosts").json() == []


def test_admin_does_not_see_other_peoples_hosts_in_the_normal_list(admin_client, make_user, login):
    make_user("hana")
    make_host(login("hana"), "private")
    assert admin_client.get("/api/hosts").json() == []  # the admin panel is the place for that
    assert admin_client.get("/api/hosts/1").status_code == 404


def test_stats(admin_client, make_user, login):
    make_user("ivy", active=False)
    make_user("joe")
    joe = login("joe")
    created = make_host(joe)
    joe.post("/api/ingest", json={"cpu_percent": 1, "memory_percent": 2, "disk_percent": 3}, headers={"X-API-Key": created["api_key"]})
    s = admin_client.get("/api/admin/stats").json()
    assert s == {"users": 3, "admins": 1, "disabled_users": 1, "hosts": 1, "hosts_online": 1, "metrics": 1}


def test_disabled_owner_cannot_ingest(admin_client, make_user, login):
    uid = make_user("kim")
    kim = login("kim")
    key = make_host(kim)["api_key"]
    body = {"cpu_percent": 1, "memory_percent": 2, "disk_percent": 3}
    assert kim.post("/api/ingest", json=body, headers={"X-API-Key": key}).status_code == 201
    admin_client.patch(f"/api/admin/users/{uid}", json={"is_active": False})
    assert admin_client.post("/api/ingest", json=body, headers={"X-API-Key": key}).status_code == 401


@pytest.mark.parametrize("path", ["/api/admin/users?limit=0", "/api/admin/users?limit=501", "/api/admin/users?skip=-1"])
def test_paging_limits(admin_client, path):
    assert admin_client.get(path).status_code == 422

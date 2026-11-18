"""Сквозной сценарий мини-приложения: анкета → лента → лайк → мэтч → удаление.

Авторизация в тестах — режим разработки (WEBAPP_DEV_AUTH=1, см. conftest.py).
"""

import pytest
from fastapi.testclient import TestClient

from webapp.main import app

PROFILE = {
    "name": "Аня",
    "city": "Новосибирск",
    "university": "НГУ",
    "degree": "бакалавриат",
    "course": 3,
    "direction": "Прикладная информатика",
    "role": "дизайн",
    "looking_for": "хакатон",
    "interests": ["python", "ML", "питон"],
    "about": "Делаю интерфейсы",
    "github": "github.com/anya",
    "username": "@anya",
}


def headers(name="anya"):
    return {"Authorization": f"dev {name}", "X-Platform": "web"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_without_auth_is_401(client):
    assert client.get("/api/me").status_code == 401
    bad = {"Authorization": "tma auth_date=1&hash=00", "X-Platform": "tg"}
    assert client.get("/api/me", headers=bad).status_code == 401


def test_full_flow(client):
    me = client.get("/api/me", headers=headers()).json()
    assert me["profile"] is None
    assert "дизайн" in me["options"]["roles"]

    # Без согласия анкету не создаём
    assert client.put("/api/profile", json=PROFILE, headers=headers()).status_code == 400

    # Проверки как в боте: ссылки, мат, неверный GitHub, роль не из списка
    bad = {**PROFILE, "consent": True, "about": "заходи на site.ru", "github": "gitlab.com/x/y/z", "role": "босс"}
    r = client.put("/api/profile", json=bad, headers=headers())
    assert r.status_code == 422
    assert {"about", "github", "role"} <= set(r.json()["errors"])

    r = client.put("/api/profile", json={**PROFILE, "consent": True}, headers=headers())
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["github"] == "https://github.com/anya"
    assert saved["interests"] == ["python", "ML"]  # «питон» — синоним python
    assert saved["contact"] == "@anya"

    feed = client.get("/api/feed", headers=headers()).json()
    assert feed["items"], "тестовые анкеты должны попасть в ленту"
    first = feed["items"][0]
    assert "contact" not in first["profile"], "контакт до мэтча скрыт"
    assert first["explain"]

    # Лайк тестовой анкете — она лайкает в ответ, получаем мэтч с контактом
    r = client.post("/api/swipe", json={"to_id": first["profile"]["id"], "action": "like", "message": "Привет!"}, headers=headers())
    assert r.status_code == 200
    assert r.json()["matched"] is True
    assert r.json()["partner"]["contact"]

    # Пропуск и ссылка в сообщении
    second = feed["items"][1]["profile"]["id"]
    assert client.post("/api/swipe", json={"to_id": second, "action": "skip"}, headers=headers()).json() == {"matched": False}
    third = feed["items"][2]["profile"]["id"]
    r = client.post("/api/swipe", json={"to_id": third, "action": "like", "message": "пиши на t.me/x"}, headers=headers())
    assert r.status_code == 422

    ids_after = {i["profile"]["id"] for i in client.get("/api/feed", headers=headers()).json()["items"]}
    assert first["profile"]["id"] not in ids_after and second not in ids_after

    matches = client.get("/api/matches", headers=headers()).json()["items"]
    assert [m["profile"]["id"] for m in matches] == [first["profile"]["id"]]
    assert matches[0]["my_message"] == "Привет!"

    # Настройки поиска сохраняются в базе
    assert client.put("/api/settings", json={"search_mode": "city"}, headers=headers()).json() == {"search_mode": "city"}
    assert client.get("/api/me", headers=headers()).json()["search_mode"] == "city"
    city_feed = client.get("/api/feed", headers=headers()).json()["items"]
    assert all(i["profile"]["city"] == "Новосибирск" for i in city_feed)

    # Сброс пропусков возвращает пропущенную анкету
    client.post("/api/feed/reset-skips", headers=headers())
    client.put("/api/settings", json={"search_mode": "all"}, headers=headers())
    feed_ids = set()
    data = client.get("/api/feed", headers=headers()).json()
    feed_ids |= {i["profile"]["id"] for i in data["items"]}
    assert data["skipped"] == 0

    # Видимость
    assert client.post("/api/profile/visibility", json={"active": False}, headers=headers()).json() == {"is_active": False}

    # Удаление всех данных
    assert client.delete("/api/profile", headers=headers()).status_code == 200
    assert client.get("/api/me", headers=headers()).json()["profile"] is None
    assert client.get("/api/feed", headers=headers()).status_code == 404


def test_two_real_users_match(client):
    for name in ("bob", "kate"):
        r = client.put("/api/profile", json={**PROFILE, "name": name, "username": f"@{name}", "consent": True}, headers=headers(name))
        assert r.status_code == 200
    r = client.post("/api/swipe", json={"to_id": "dev-kate", "action": "like"}, headers=headers("bob"))
    assert r.json() == {"matched": False}
    assert client.get("/api/me", headers=headers("kate")).json()["stats"]["incoming_likes"] == 1
    r = client.post("/api/swipe", json={"to_id": "dev-bob", "action": "like"}, headers=headers("kate"))
    assert r.json()["matched"] is True
    assert r.json()["partner"]["contact"] == "@bob"


def test_photo_upload_checks_type(client):
    client.put("/api/profile", json={**PROFILE, "consent": True}, headers=headers("pic"))
    r = client.post("/api/profile/photo", files={"file": ("x.txt", b"not an image", "text/plain")}, headers=headers("pic"))
    assert r.status_code == 415
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    r = client.post("/api/profile/photo", files={"file": ("a.png", png, "image/png")}, headers=headers("pic"))
    assert r.status_code == 200
    url = r.json()["photo_url"]
    assert client.get(url).status_code == 200
    assert client.get("/api/me", headers=headers("pic")).json()["profile"]["photo_url"] == url

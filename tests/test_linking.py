"""Одна анкета на человека в Telegram и MAX: код привязки, защита от дублей, удаление везде."""

import pytest
from fastapi.testclient import TestClient

from db.repo import contact_keys
from webapp.main import app

PROFILE = {
    "name": "Лёша",
    "city": "Новосибирск",
    "university": "НГУ",
    "degree": "магистратура",
    "course": 1,
    "direction": "Экономика",
    "role": "финансы",
    "looking_for": "кейс-чемпионат",
    "interests": ["экономика", "аналитика"],
    "username": "@lesha_nsu",
    "consent": True,
}

TG = {"Authorization": "dev tg:5001", "X-Platform": "web"}
MAX = {"Authorization": "dev max:7001", "X-Platform": "web"}
MAX2 = {"Authorization": "dev max:7002", "X-Platform": "web"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_contact_keys_normalize_phone_nick_email():
    assert contact_keys("ТГ: @Lesha_NSU") == {"nick:lesha_nsu"}
    assert contact_keys("8 (913) 123-45-67") == {"phone:79131234567"}
    assert contact_keys("+7 913 123 45 67") == {"phone:79131234567"}
    assert contact_keys("lesha@nsu.ru") == {"email:lesha@nsu.ru"}


def test_second_messenger_joins_the_same_profile(client):
    # 1. Анкета создана в Telegram
    r = client.put("/api/profile", json=PROFILE, headers=TG)
    assert r.status_code == 200, r.text
    tg_profile_id = r.json()["id"]
    assert tg_profile_id == "tg:5001"

    # 2. Тот же человек открывает MAX и пытается создать вторую анкету с тем же контактом
    r = client.put("/api/profile", json={**PROFILE, "username": "ТГ: @Lesha_NSU"}, headers=MAX)
    assert r.status_code == 409
    assert r.json()["code"] == "duplicate" and r.json()["platform"] == "Telegram"

    # 3. Неверный код
    r = client.post("/api/link", json={"code": "WRONG123"}, headers=MAX)
    assert r.status_code == 400 and r.json()["code"] == "bad_code"

    # 4. В Telegram получает код, в MAX вводит его
    code = client.post("/api/link/code", headers=TG).json()["code"]
    assert len(code) == 8
    assert client.post("/api/link", json={"code": code.lower()}, headers=MAX).json() == {"ok": True}

    # Код одноразовый
    r = client.post("/api/link", json={"code": code}, headers=MAX2)
    assert r.status_code == 400

    # 5. Из MAX видна та же анкета, оба мессенджера подключены
    me = client.get("/api/me", headers=MAX).json()
    assert me["profile"]["id"] == tg_profile_id
    assert me["linked"] == ["max", "tg"]

    # Создать вторую анкету из MAX уже нельзя — PUT обновляет общую
    r = client.put("/api/profile", json={**PROFILE, "about": "из MAX"}, headers=MAX)
    assert r.status_code == 200 and r.json()["id"] == tg_profile_id
    assert client.get("/api/me", headers=TG).json()["profile"]["about"] == "из MAX"

    # 6. Лайк из MAX — это лайк анкеты, мэтч виден и в Telegram
    feed = client.get("/api/feed", headers=MAX).json()["items"]
    target = feed[0]["profile"]["id"]
    assert client.post("/api/swipe", json={"to_id": target, "action": "like"}, headers=MAX).json()["matched"]
    tg_matches = client.get("/api/matches", headers=TG).json()["items"]
    assert [m["profile"]["id"] for m in tg_matches] == [target]
    # и в ленте Telegram этого человека больше нет
    assert target not in {i["profile"]["id"] for i in client.get("/api/feed", headers=TG).json()["items"]}

    # 7. Второй аккаунт MAX к той же анкете не подключить
    code = client.post("/api/link/code", headers=TG).json()["code"]
    r = client.post("/api/link", json={"code": code}, headers=MAX2)
    assert r.status_code == 400 and r.json()["code"] == "platform_taken"

    # 8. Удаление из MAX удаляет анкету везде
    assert client.delete("/api/profile", headers=MAX).status_code == 200
    assert client.get("/api/me", headers=TG).json()["profile"] is None
    assert client.get("/api/me", headers=MAX).json()["profile"] is None


def test_linking_when_both_profiles_exist_requires_replace(client):
    a = {"Authorization": "dev tg:6001", "X-Platform": "web"}
    b = {"Authorization": "dev max:8001", "X-Platform": "web"}
    client.put("/api/profile", json={**PROFILE, "username": "@first_one"}, headers=a)
    client.put("/api/profile", json={**PROFILE, "username": "@second_one"}, headers=b)
    code = client.post("/api/link/code", headers=a).json()["code"]
    r = client.post("/api/link", json={"code": code}, headers=b)
    assert r.status_code == 409 and r.json()["code"] == "has_profile"
    assert client.post("/api/link", json={"code": code, "replace": True}, headers=b).json() == {"ok": True}
    assert client.get("/api/me", headers=b).json()["profile"]["contact"] == "@first_one"


def test_force_new_profile_when_not_the_same_person(client):
    a = {"Authorization": "dev tg:6101", "X-Platform": "web"}
    b = {"Authorization": "dev max:8101", "X-Platform": "web"}
    client.put("/api/profile", json={**PROFILE, "username": "+7 900 000-00-01"}, headers=a)
    r = client.put("/api/profile", json={**PROFILE, "username": "89000000001"}, headers=b)
    assert r.status_code == 409
    r = client.put("/api/profile", json={**PROFILE, "username": "89000000001", "force_new": True}, headers=b)
    assert r.status_code == 200 and r.json()["id"] == "8101"


def test_legal_pages(client):
    for path in ("/legal/consent", "/legal/privacy"):
        r = client.get(path)
        assert r.status_code == 200
        assert "152-ФЗ" in r.text and "{{" not in r.text
    me = client.get("/api/me", headers=TG).json()
    assert me["legal"]["law_url"].startswith("https://")

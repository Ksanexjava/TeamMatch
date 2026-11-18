import hashlib
import hmac
import json
import time
from urllib.parse import quote

import pytest

from webapp import auth

TOKEN = "123456:TEST-TOKEN"


def sign(fields: dict, token: str = TOKEN) -> str:
    """Собрать initData так же, как это делают Telegram и MAX."""
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields = {**fields, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()}
    return "&".join(f"{k}={quote(str(v), safe='')}" for k, v in fields.items())


def fields(user_id=42, auth_date=None, **extra):
    return {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAE",
        "user": json.dumps({"id": user_id, "first_name": "Аня", "username": "anya"}, ensure_ascii=False),
        **extra,
    }


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setattr(auth, "_token_for", lambda platform: TOKEN)


def test_telegram_user_gets_prefixed_id():
    user = auth.validate("tg", sign(fields(start_param="hack42")))
    assert user.user_id == "tg:42"
    assert user.username == "anya"
    assert user.start_param == "hack42"


def test_max_user_keeps_plain_id_like_the_bot():
    user = auth.validate("max", sign(fields(user_id=777, chat=json.dumps({"id": 1, "type": "DIALOG"}))))
    assert user.user_id == "777"


def test_tampered_data_is_rejected():
    data = sign(fields()).replace("anya", "admin")
    with pytest.raises(auth.AuthError):
        auth.validate("tg", data)


def test_wrong_token_is_rejected(monkeypatch):
    data = sign(fields(), token="999:OTHER")
    with pytest.raises(auth.AuthError):
        auth.validate("tg", data)


def test_expired_data_is_rejected():
    old = int(time.time()) - 10 * 86400
    with pytest.raises(auth.AuthError):
        auth.validate("tg", sign(fields(auth_date=old)))


def test_duplicate_keys_are_rejected():
    with pytest.raises(auth.AuthError):
        auth.validate("tg", sign(fields()) + "&user=%7B%22id%22%3A1%7D")


def test_unknown_platform_is_rejected():
    with pytest.raises(auth.AuthError):
        auth.validate("vk", sign(fields()))

"""Проверка подлинности запуска мини-приложения (initData).

Telegram и MAX подписывают initData одинаково:
  secret_key = HMAC_SHA256(key="WebAppData", msg=<токен бота>)
  hash       = hex(HMAC_SHA256(key=secret_key, msg=data_check_string))
где data_check_string — все пары key=value, кроме hash, отсортированные по ключу
и склеенные через \n. Документация:
  Telegram — https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
  MAX      — https://dev.max.ru/docs/webapps/validation

Токены ботов живут только на сервере. Браузер присылает initData как есть,
сервер проверяет подпись и только после этого доверяет user.id.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import unquote

from config import settings
from messengers import ids

PLATFORMS = ("tg", "max")


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class WebAppUser:
    user_id: str          # id в общем пуле анкет (tg:123 или 123)
    platform: str         # tg / max / dev
    first_name: str
    last_name: str
    username: str
    start_param: str
    profile_id: str = ""  # id анкеты; заполняет webapp.main.current_user (аккаунт может быть привязан)


def _token_for(platform: str) -> str:
    if platform == "tg":
        return settings.telegram_bot_token
    if platform == "max":
        return settings.bot_token
    return ""


def parse_init_data(init_data: str) -> dict[str, str]:
    """Строка initData → словарь. Каждый ключ должен встречаться ровно один раз."""
    result: dict[str, str] = {}
    for chunk in (init_data or "").split("&"):
        if not chunk:
            continue
        key, sep, value = chunk.partition("=")
        if not sep:
            raise AuthError("Неверный формат initData")
        key, value = unquote(key), unquote(value)
        if key in result:
            raise AuthError(f"Ключ {key} повторяется")
        result[key] = value
    return result


def check_signature(fields: dict[str, str], bot_token: str) -> bool:
    received = fields.get("hash", "")
    if not received or not bot_token:
        return False
    check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields) if k != "hash")
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received.lower())


def validate(platform: str, init_data: str, now: float | None = None) -> WebAppUser:
    if platform not in PLATFORMS:
        raise AuthError("Неизвестная площадка")
    fields = parse_init_data(init_data)
    if not check_signature(fields, _token_for(platform)):
        raise AuthError("Подпись initData не сошлась")

    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError as exc:
        raise AuthError("Неверный auth_date") from exc
    # Telegram присылает секунды; на случай миллисекунд в MAX — приводим.
    if auth_date > 10**11:
        auth_date //= 1000
    current = now if now is not None else time.time()
    if settings.init_data_ttl and current - auth_date > settings.init_data_ttl:
        raise AuthError("initData устарела — открой приложение заново")

    try:
        user = json.loads(fields.get("user") or "{}")
    except json.JSONDecodeError as exc:
        raise AuthError("Неверное поле user") from exc
    if not user.get("id"):
        raise AuthError("В initData нет пользователя")

    user_id = ids.from_telegram(user["id"]) if platform == "tg" else ids.from_max(user["id"])
    return WebAppUser(
        user_id=user_id,
        platform=platform,
        first_name=user.get("first_name") or "",
        last_name=user.get("last_name") or "",
        username=user.get("username") or "",
        start_param=fields.get("start_param") or "",
    )


def dev_user(raw: str) -> WebAppUser:
    """Локальная разработка без мессенджера (WEBAPP_DEV_AUTH=1).

    «dev <имя>»       — тестовый пользователь вне мессенджеров;
    «dev tg:<число>»  — как будто открыли из Telegram;
    «dev max:<число>» — как будто открыли из MAX (нужно, чтобы проверить привязку аккаунтов).
    """
    platform, _, num = (raw or "").partition(":")
    if platform in PLATFORMS and num.isdigit():
        user_id = ids.from_telegram(num) if platform == "tg" else ids.from_max(num)
        return WebAppUser(user_id=user_id, platform=platform, first_name=f"{platform}{num}",
                          last_name="", username=f"{platform}{num}", start_param="")
    name = "".join(ch for ch in (raw or "local") if ch.isalnum())[:20] or "local"
    return WebAppUser(
        user_id=f"dev-{name}", platform="dev", first_name=name.capitalize(),
        last_name="", username=name, start_param="",
    )

"""Идентификаторы пользователей в общем пуле анкет.

MAX и Telegram — разные пространства id, а profiles.user_id — первичный ключ.
Чтобы не мигрировать боевую базу, id из MAX остаются как есть (только цифры),
а id из Telegram хранятся с префиксом: tg:<id>. Тестовые анкеты — u001…
"""

TELEGRAM_PREFIX = "tg:"


def from_telegram(tg_user_id: int | str) -> str:
    return f"{TELEGRAM_PREFIX}{tg_user_id}"


def from_max(max_user_id: int | str) -> str:
    return str(max_user_id)


def platform_of(user_id: str) -> str:
    """max / tg / test."""
    uid = str(user_id)
    if uid.startswith(TELEGRAM_PREFIX):
        return "tg"
    if uid.isdigit():
        return "max"
    return "test"


def telegram_chat_id(user_id: str) -> int | None:
    uid = str(user_id)
    if not uid.startswith(TELEGRAM_PREFIX):
        return None
    raw = uid[len(TELEGRAM_PREFIX):]
    return int(raw) if raw.isdigit() else None

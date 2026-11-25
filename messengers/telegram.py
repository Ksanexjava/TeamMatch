"""Отправка сообщений в Telegram без aiogram — для процессов, где нет своего Telegram-бота
(бот MAX и мини-приложение шлют отсюда уведомления пользователям Telegram).

Сам Telegram-бот (диалог, кнопки, long polling) — пакет tgbot/.
"""

import logging

import httpx

from config import settings

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def api_url(method: str) -> str:
    """Адрес метода Bot API: свой ретранслятор, если задан, иначе Telegram напрямую."""
    return f"{settings.telegram_api_base or TELEGRAM_API}/bot{settings.telegram_bot_token}/{method}"


def enabled() -> bool:
    return bool(settings.telegram_bot_token)


async def call(method: str, payload: dict | None = None, timeout: float = 15):
    url = api_url(method)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload or {})
    data = response.json()
    if not data.get("ok"):
        # В текст ошибки попадает только описание от Telegram — URL с токеном не логируем.
        raise RuntimeError(f"Telegram {method}: {data.get('description')}")
    return data.get("result")


def open_app_markup(text: str = "Открыть Тиммейт", start_param: str = "") -> dict | None:
    if not settings.telegram_webapp_url or not settings.telegram_webapp_button:
        return None
    url = settings.telegram_webapp_url + "/"
    if start_param:
        url += f"?startapp={start_param}"
    return {"inline_keyboard": [[{"text": text, "web_app": {"url": url}}]]}


def default_markup() -> dict:
    """Кнопка под уведомлением: мини-приложение, если оно подключено, иначе лента в чат-боте."""
    return open_app_markup() or {"inline_keyboard": [[{"text": "🔍 Открыть ленту", "callback_data": "menu:feed"}]]}


async def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text, "reply_markup": reply_markup or default_markup()}
    await call("sendMessage", payload)

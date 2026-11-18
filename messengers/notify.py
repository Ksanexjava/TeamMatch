"""Уведомления пользователю в его мессенджер.

Пул анкет общий: пользователь MAX может лайкнуть пользователя Telegram и наоборот,
поэтому площадка выбирается по id получателя (см. messengers/ids.py).
"""

import logging

from config import settings
from messengers import ids, telegram

log = logging.getLogger(__name__)

_max_bot = None


def _get_max_bot():
    """Свой экземпляр бота MAX — для процесса мини-приложения, где бота нет."""
    global _max_bot
    if _max_bot is None and settings.bot_token:
        from maxapi import Bot

        _max_bot = Bot(token=settings.bot_token)
    return _max_bot


async def send(user_id: str, text: str, *, max_bot=None, max_attachments=None, tg_text: str | None = None,
               tg_markup: dict | None = None) -> None:
    """Отправить текст. Ошибки глушим: уведомление не должно ломать лайк.

    tg_text — свой вариант текста для Telegram, где вместо кнопок бота MAX
    под сообщением одна кнопка «Открыть Тиммейт».
    """
    platform = ids.platform_of(user_id)
    try:
        if platform == "tg":
            if telegram.enabled():
                await telegram.send_message(ids.telegram_chat_id(user_id), tg_text or text, tg_markup)
        elif platform == "max":
            bot = max_bot or _get_max_bot()
            if bot is not None:
                await bot.send_message(user_id=int(user_id), text=text, attachments=max_attachments or [])
    except Exception as exc:
        log.warning("Не удалось отправить уведомление (%s): %s", platform, exc)


async def send_to_profile(profile_id: str, text: str, **kwargs) -> None:
    """Уведомить владельца анкеты во всех подключённых мессенджерах."""
    from db import repo  # локальный импорт: repo импортирует messengers.ids

    for account_id in await repo.linked_account_ids(profile_id):
        await send(account_id, text, **kwargs)

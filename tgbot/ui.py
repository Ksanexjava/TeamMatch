"""Кнопки живут только у последнего сообщения бота в чате.

Без этого при лагах сети, двойном /start или двойном тапе в чате оставались несколько
«живых» меню, и нажатия на старые путали сценарий. Три слоя защиты:

1. KeyboardTracker (на уровне запросов к Telegram): после каждого нового сообщения бота
   у предыдущего снимаются кнопки. Работает для любого экрана, обработчики об этом не знают.
2. StaleCallbackGuard: нажатие на кнопку сообщения старее последнего не выполняется —
   бот отвечает «меню устарело» и убирает с него кнопки.
3. PerUserLock: апдейты одного человека обрабатываются по очереди, поэтому двойной тап
   не запускает два обработчика параллельно (второй упирается в защиту из п. 2).

Номер последнего сообщения хранится в хранилище состояний (Redis на сервере) в отдельном
пространстве — state.clear() в обработчиках его не стирает, и он переживает перезапуск.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.methods import (
    EditMessageCaption, EditMessageReplyMarkup, EditMessageText, SendMessage, SendPhoto,
)
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, TelegramObject, Update

log = logging.getLogger(__name__)

STALE_TEXT = "Это меню устарело — пользуйся последним сообщением 👇"
DESTINY = "ui"  # отдельное пространство в хранилище, не трогается state.clear()


class KeyboardTracker(BaseRequestMiddleware):
    """Запоминает последнее сообщение бота в чате и снимает кнопки с предыдущего."""

    def __init__(self, storage: BaseStorage):
        self.storage = storage
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    def key(self, bot: Bot, chat_id: int) -> StorageKey:
        return StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=chat_id, destiny=DESTINY)

    async def latest(self, bot: Bot, chat_id: int) -> dict:
        return await self.storage.get_data(self.key(bot, chat_id))

    async def __call__(self, make_request, bot: Bot, method) -> Any:
        if isinstance(method, (SendMessage, SendPhoto)) and isinstance(method.chat_id, int):
            chat_id = method.chat_id
            async with self._locks[chat_id]:
                result = await make_request(bot, method)
                if isinstance(result, Message):
                    prev = await self.latest(bot, chat_id)
                    has_kb = isinstance(method.reply_markup, InlineKeyboardMarkup)
                    await self.storage.set_data(self.key(bot, chat_id), {"id": result.message_id, "kb": has_kb})
                    if prev.get("kb") and prev.get("id") and prev["id"] != result.message_id:
                        await self._drop(bot, chat_id, prev["id"])
                return result

        if isinstance(method, (EditMessageText, EditMessageCaption, EditMessageReplyMarkup)) \
                and isinstance(method.chat_id, int) and method.message_id:
            result = await make_request(bot, method)
            data = await self.latest(bot, method.chat_id)
            if data.get("id") == method.message_id:
                data["kb"] = isinstance(method.reply_markup, InlineKeyboardMarkup)
                await self.storage.set_data(self.key(bot, method.chat_id), data)
            return result

        return await make_request(bot, method)

    @staticmethod
    async def _drop(bot: Bot, chat_id: int, message_id: int) -> None:
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        except TelegramBadRequest:
            pass  # уже без кнопок или слишком старое для правки
        except Exception as exc:  # сеть и т.п. — не повод ронять ответ пользователю
            log.debug("Не удалось снять кнопки: %s", exc)


class StaleCallbackGuard(BaseMiddleware):
    """Не выполняет нажатия на кнопки сообщений, которые старее последнего сообщения бота."""

    def __init__(self, tracker_storage: BaseStorage):
        self.storage = tracker_storage

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
            bot: Bot = data["bot"]
            chat_id = event.message.chat.id
            key = StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=chat_id, destiny=DESTINY)
            latest = (await self.storage.get_data(key)).get("id")
            if latest and event.message.message_id < latest:
                await event.answer(STALE_TEXT, show_alert=False)
                try:
                    await event.message.edit_reply_markup(reply_markup=None)
                except TelegramBadRequest:
                    pass
                return None
        return await handler(event, data)


class PerUserLock(BaseMiddleware):
    """Апдейты одного пользователя — строго по очереди."""

    def __init__(self):
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = None
        if isinstance(event, Update):
            inner = event.message or event.callback_query
            user = inner.from_user if inner else None
        if user is None:
            return await handler(event, data)
        async with self._locks[user.id]:
            return await handler(event, data)


def setup_dispatcher(dp: Dispatcher) -> None:
    dp.update.outer_middleware(PerUserLock())
    dp.callback_query.outer_middleware(StaleCallbackGuard(dp.storage))


def attach_bot(bot: Bot, dp: Dispatcher) -> None:
    bot.session.middleware(KeyboardTracker(dp.storage))

"""Запуск Telegram-бота: python -m tgbot.main

Работает через long polling — входящие порты, домен и HTTPS не нужны.
Если задан WEBAPP_URL, дополнительно ставит кнопку мини-приложения в меню чата.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo

from config import settings
from db.session import init_db
from tgbot.handlers import router

log = logging.getLogger("tgbot")

COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="profile", description="Моя анкета"),
    BotCommand(command="link", description="Подключить анкету из MAX"),
    BotCommand(command="help", description="Справка"),
]


def build_storage() -> BaseStorage:
    """Шаги анкеты: Redis (переживает перезапуск) или память (локальный запуск)."""
    if settings.redis_url:
        from aiogram.fsm.storage.redis import RedisStorage

        log.info("Состояния анкет хранятся в Redis")
        return RedisStorage.from_url(settings.redis_url)
    log.info("REDIS_URL не задан — состояния анкет хранятся в памяти")
    return MemoryStorage()


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=build_storage())
    dp.include_router(router)
    return dp


async def prepare_db() -> None:
    # Тестовые анкеты загружает бот MAX; если он не запущен (локально) — загрузим сами.
    for attempt in range(5):
        try:
            await init_db(seed=not settings.bot_token)
            return
        except Exception as exc:  # сервисы стартуют одновременно и могут столкнуться на create_all
            log.warning("init_db (попытка %s): %s", attempt + 1, exc)
            await asyncio.sleep(2)


async def setup_bot(bot: Bot) -> None:
    await bot.set_my_commands(COMMANDS)
    if settings.webapp_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text="Открыть", web_app=WebAppInfo(url=settings.webapp_url + "/")))
    else:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    # Если на токене когда-то стоял вебхук, long polling не заработает.
    await bot.delete_webhook(drop_pending_updates=False)


async def main() -> None:
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    if not settings.telegram_bot_token:
        raise SystemExit("Не задан TELEGRAM_BOT_TOKEN. Впиши токен от @BotFather в .env.")
    await prepare_db()
    bot = Bot(token=settings.telegram_bot_token)
    me = await bot.get_me()
    log.info("Telegram-бот запущен: @%s", me.username)
    await setup_bot(bot)
    await build_dispatcher().start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

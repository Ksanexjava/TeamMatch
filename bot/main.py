import asyncio
import logging

from maxapi import Bot, Dispatcher
from maxapi.context.context import MemoryContext

from bot.handlers import routers
from config import settings
from db.session import init_db

log = logging.getLogger("bot")


def build_dispatcher() -> Dispatcher:
    """Где хранить шаги анкеты: Redis (переживает перезапуск) или память (для локального запуска)."""
    if settings.redis_url:
        from maxapi.context.context import RedisContext
        from redis.asyncio import Redis

        dp = Dispatcher(storage=RedisContext, redis_client=Redis.from_url(settings.redis_url))
        log.info("Состояния анкет хранятся в Redis")
    else:
        dp = Dispatcher(storage=MemoryContext)
        log.info("REDIS_URL не задан — состояния анкет хранятся в памяти")
    dp.include_routers(*routers)
    return dp


async def main() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    if not settings.bot_token:
        raise SystemExit("Не задан MAX_BOT_TOKEN. Скопируй .env.example в .env и впиши токен.")

    await init_db()
    bot = Bot(token=settings.bot_token)
    dp = build_dispatcher()
    log.info("Бот запущен, жду сообщения…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

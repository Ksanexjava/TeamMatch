# db/session.py
# Подключение к базе и первичная подготовка: создание таблиц и загрузка тестовых анкет.

import json
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from db.models import Base, Profile

log = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

TEST_PROFILES_PATH = Path(__file__).resolve().parent.parent / "data" / "test_profiles.json"


async def init_db() -> None:
    """Создаёт таблицы (если их нет) и один раз загружает тестовые анкеты.

    Для MVP вместо миграций Alembic используем create_all: таблицы создаются
    при первом запуске. Если меняете модели — удалите том с базой
    (docker compose down -v) и запустите заново.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_test_profiles()


async def seed_test_profiles() -> None:
    """Загружает data/test_profiles.json, если тестовых анкет в базе ещё нет.

    Это ТЕСТОВЫЕ данные (сгенерированы tools/generate_test_profiles.py),
    они помечены is_test=True — так и пишем в README для проверяющих.
    """
    if not settings.seed_test_profiles or not TEST_PROFILES_PATH.exists():
        return
    async with Session() as session:
        count = await session.scalar(select(func.count()).select_from(Profile).where(Profile.is_test))
        if count:
            return
        raw = json.loads(TEST_PROFILES_PATH.read_text(encoding="utf-8"))
        for item in raw:
            session.add(
                Profile(
                    user_id=str(item["user_id"]),
                    name=item.get("name", ""),
                    university=item.get("university", ""),
                    degree=item.get("degree", "бакалавриат"),   # у тестовых анкет курсы 1–4
                    course=item.get("course"),
                    direction=item.get("direction", ""),
                    city=item.get("city", ""),
                    role=item.get("role", ""),
                    looking_for=item.get("looking_for", ""),
                    interests=item.get("interests", []),
                    about=item.get("about", ""),
                    github=item.get("github", ""),
                    username=item.get("username", ""),
                    is_test=True,
                )
            )
        await session.commit()
        log.info("Загружено тестовых анкет: %s", len(raw))

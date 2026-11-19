# db/session.py

import json
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from db.models import Base, Event, Profile

log = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

TEST_PROFILES_PATH = Path(__file__).resolve().parent.parent / "data" / "test_profiles.json"
TEST_EVENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "test_events.json"

async def init_db(seed: bool = True) -> None:
    """Создаёт таблицы (если их нет) и один раз загружает тестовые анкеты.

    Для MVP вместо миграций Alembic используем create_all: таблицы создаются
    при первом запуске. Если меняете модели — удалите том с базой
    (docker compose down -v) и запустите заново.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if seed:
        await seed_test_profiles()
    await seed_events()

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
                    degree=item.get("degree", "бакалавриат"),
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


async def seed_events() -> None:
    """Загружает data/test_events.json, если таблица мероприятий пуста.

    В отличие от анкет, события грузятся всегда: без них лента пустая,
    а подбор под мероприятие проверить нечем. Заполняются руками — парсера нет.
    """
    if not TEST_EVENTS_PATH.exists():
        return
    async with Session() as session:
        if await session.scalar(select(func.count()).select_from(Event)):
            return
        raw = json.loads(TEST_EVENTS_PATH.read_text(encoding="utf-8"))
        for item in raw:
            session.add(
                Event(
                    title=item["title"],
                    organizer=item.get("organizer", ""),
                    url=item.get("url", ""),
                    city=item.get("city", ""),
                    format=item.get("format", ""),
                    team_size=item.get("team_size", ""),
                    starts_on=date.fromisoformat(item["starts_on"]) if item.get("starts_on") else None,
                    deadline_on=date.fromisoformat(item["deadline_on"]) if item.get("deadline_on") else None,
                    about=item.get("about", ""),
                )
            )
        await session.commit()
        log.info("Загружено мероприятий: %s", len(raw))

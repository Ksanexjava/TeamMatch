# db/repo.py
# Все обращения к базе — только через эти функции.
# Обработчики бота (bot/handlers/*) не пишут SQL сами, а вызывают repo.
#
# Для Миши: всё, что нужно ленте и мэтчам, уже здесь —
#   profile = await repo.get_profile(user_id)          → dict или None
#   pool    = await repo.list_active_profiles()        → list[dict] для build_feed()
#   swiped  = await repo.get_swiped_ids(user_id)       → set[str] для build_feed()
#   await repo.save_swipe(from_id, to_id, liked=True)  → записать лайк/дизлайк
#   likes   = await repo.get_likes_involving(user_id)  → list[dict] для is_match()/matches_for()

from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select

from db.models import Profile, Swipe
from db.session import Session

# ── Профили ──────────────────────────────────────────────────────────────────


async def get_profile(user_id: str | int) -> dict | None:
    """Анкета пользователя в формате Миши или None, если анкеты нет."""
    async with Session() as session:
        profile = await session.get(Profile, str(user_id))
        return profile.to_dict() if profile else None


async def has_profile(user_id: str | int) -> bool:
    return await get_profile(user_id) is not None


async def save_profile(user_id: str | int, data: dict) -> dict:
    """Создаёт или обновляет анкету. data — словарь с полями Profile.

    interests должны быть уже нормализованы (core/interests.py).
    """
    allowed = {
        "name", "university", "course", "city", "role", "looking_for",
        "interests", "about", "github", "username", "photo",
    }
    clean = {k: v for k, v in data.items() if k in allowed}
    async with Session() as session:
        profile = await session.get(Profile, str(user_id))
        if profile is None:
            profile = Profile(user_id=str(user_id), consent_at=datetime.now(timezone.utc), **clean)
            session.add(profile)
        else:
            for key, value in clean.items():
                setattr(profile, key, value)
        await session.commit()
        return profile.to_dict()


async def set_active(user_id: str | int, is_active: bool) -> None:
    """Скрыть/показать анкету в ленте других пользователей."""
    async with Session() as session:
        profile = await session.get(Profile, str(user_id))
        if profile:
            profile.is_active = is_active
            await session.commit()


async def delete_profile(user_id: str | int) -> None:
    """Удалить анкету и все свайпы пользователя (право на удаление данных, 152-ФЗ)."""
    async with Session() as session:
        profile = await session.get(Profile, str(user_id))
        if profile:
            await session.delete(profile)
        swipes = await session.scalars(
            select(Swipe).where(or_(Swipe.from_id == str(user_id), Swipe.to_id == str(user_id)))
        )
        for swipe in swipes:
            await session.delete(swipe)
        await session.commit()


async def list_active_profiles() -> list[dict]:
    """Все видимые анкеты — вход для core.recommendations.build_feed().

    Для MVP грузим всех в память: при сотнях анкет это быстро.
    При масштабировании — фильтровать по looking_for/интересам прямо в SQL.
    """
    async with Session() as session:
        rows = await session.scalars(select(Profile).where(Profile.is_active.is_(True)))
        return [p.to_dict() for p in rows]


# ── Свайпы, лайки, мэтчи ─────────────────────────────────────────────────────


async def save_swipe(from_id: str | int, to_id: str | int, liked: bool, message: str = "") -> None:
    """Записывает лайк (liked=True) или пропуск (liked=False). Повторный свайп перезаписывает старый."""
    async with Session() as session:
        existing = await session.scalar(
            select(Swipe).where(Swipe.from_id == str(from_id), Swipe.to_id == str(to_id))
        )
        if existing:
            existing.liked = liked
            existing.message = message
        else:
            session.add(Swipe(from_id=str(from_id), to_id=str(to_id), liked=liked, message=message))
        await session.commit()


async def get_swiped_ids(user_id: str | int) -> set[str]:
    """Кого пользователь уже оценил (лайк или пропуск) — их не показываем в ленте."""
    async with Session() as session:
        rows = await session.scalars(select(Swipe.to_id).where(Swipe.from_id == str(user_id)))
        return set(rows)


async def count_skips(user_id: str | int) -> int:
    """Сколько анкет пользователь пропустил (дизлайкнул)."""
    async with Session() as session:
        return await session.scalar(
            select(func.count()).select_from(Swipe).where(Swipe.from_id == str(user_id), Swipe.liked.is_(False))
        ) or 0


async def reset_skips(user_id: str | int) -> None:
    """Забыть пропуски пользователя — пропущенные анкеты снова появятся в его ленте.

    Лайки не трогаем: лайкнутых повторно не показываем, их ответ (мэтч) ещё может прийти.
    """
    async with Session() as session:
        await session.execute(delete(Swipe).where(Swipe.from_id == str(user_id), Swipe.liked.is_(False)))
        await session.commit()


async def get_likes_involving(user_id: str | int) -> list[dict]:
    """Все лайки, где участвует пользователь, в формате Миши: [{"from_id", "to_id", "message"}].

    Передаётся в core.interactions: is_match(), matches_for(), incoming_likes().
    """
    uid = str(user_id)
    async with Session() as session:
        rows = await session.scalars(
            select(Swipe).where(Swipe.liked.is_(True), or_(Swipe.from_id == uid, Swipe.to_id == uid))
        )
        return [s.to_like_dict() for s in rows]

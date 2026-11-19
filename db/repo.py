# db/repo.py
#
# Все функции принимают id аккаунта (MAX: «123», Telegram: «tg:123») или id анкеты —
# и сами приводят его к id анкеты через resolve_id(). Поэтому бот и мини-приложение
# не знают про привязку аккаунтов: человек, подключивший второй мессенджер,
# просто попадает в свою единственную анкету.

import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select

from config import settings
from db.models import Account, Consent, Event, LinkCode, Profile, ProfileEvent, Swipe, UserSettings
from db.session import Session
from messengers import ids

#Аккаунты и привязка мессенджеров

LINK_CODE_TTL = timedelta(minutes=10)
# Без похожих символов (0/O, 1/I/L), чтобы код легко переписать с экрана.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LEN = 8


def _split(user_id: str) -> tuple[str, str] | None:
    """«tg:5» → ("tg", "5"), «123» → ("max", "123"); тестовые анкеты — None."""
    uid = str(user_id)
    platform = ids.platform_of(uid)
    if platform == "tg":
        return "tg", uid[len(ids.TELEGRAM_PREFIX):]
    if platform == "max":
        return "max", uid
    return None


async def resolve_id(user_id: str | int) -> str:
    """id аккаунта → id анкеты. Для непривязанного аккаунта это он сам."""
    uid = str(user_id)
    key = _split(uid)
    if key is None:
        return uid
    async with Session() as session:
        account = await session.get(Account, key)
        return account.profile_id if account else uid


async def linked_account_ids(profile_id: str) -> list[str]:
    """Все аккаунты анкеты (родной + привязанные) — куда слать уведомления."""
    pid = str(profile_id)
    result = [pid] if _split(pid) else []
    async with Session() as session:
        rows = await session.scalars(select(Account).where(Account.profile_id == pid))
        for acc in rows:
            result.append(ids.from_telegram(acc.external_id) if acc.platform == "tg" else ids.from_max(acc.external_id))
    return result


async def profile_platforms(profile_id: str) -> set[str]:
    platforms = set()
    for account_id in await linked_account_ids(profile_id):
        platforms.add(ids.platform_of(account_id))
    return platforms


async def create_link_code(user_id: str | int) -> tuple[str, datetime]:
    """Новый код привязки для анкеты. Старые коды этой анкеты сгорают."""
    pid = await resolve_id(user_id)
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))
    expires = datetime.now(timezone.utc) + LINK_CODE_TTL
    async with Session() as session:
        await session.execute(delete(LinkCode).where(LinkCode.profile_id == pid))
        session.add(LinkCode(code=code, profile_id=pid, expires_at=expires))
        await session.commit()
    return code, expires


def normalize_code(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


class LinkError(Exception):
    """Причина отказа в привязке — текст для пользователя в .message, машинный код в .code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


async def redeem_link_code(raw_code: str, account_id: str, replace: bool = False) -> str:
    """Привязать аккаунт account_id к анкете, выдавшей код. Возвращает id анкеты.

    replace=True — у аккаунта уже есть своя анкета, и человек согласился её удалить
    (иначе после привязки у него остались бы две анкеты).
    """
    key = _split(account_id)
    if key is None:
        raise LinkError("bad_account", "Привязка доступна только из Telegram и MAX")
    code = normalize_code(raw_code)
    now = datetime.now(timezone.utc)
    async with Session() as session:
        row = await session.get(LinkCode, code) if code else None
        expires = row.expires_at if row else None
        if expires is not None and expires.tzinfo is None:  # SQLite отдаёт время без зоны
            expires = expires.replace(tzinfo=timezone.utc)
        if row is None or expires < now:
            raise LinkError("bad_code", "Код не подошёл или устарел. Получи новый — он действует 10 минут")
        target = row.profile_id

    if await resolve_id(account_id) == target:
        raise LinkError("already", "Этот мессенджер уже подключён к твоей анкете")
    if key[0] in await profile_platforms(target):
        name = "Telegram" if key[0] == "tg" else "MAX"
        raise LinkError("platform_taken", f"К этой анкете уже подключён другой аккаунт {name}")

    own = await resolve_id(account_id)
    if await get_profile(own) is not None:
        if not replace:
            raise LinkError("has_profile", "Здесь у тебя уже есть анкета. Чтобы осталась одна, её нужно удалить")
        await delete_profile(own)

    async with Session() as session:
        existing = await session.get(Account, key)
        if existing:
            existing.profile_id = target
        else:
            session.add(Account(platform=key[0], external_id=key[1], profile_id=target))
        await session.execute(delete(LinkCode).where(LinkCode.code == code))
        await session.commit()
    return target


async def unlink_account(account_id: str) -> None:
    key = _split(account_id)
    if key is None:
        return
    async with Session() as session:
        await session.execute(delete(Account).where(Account.platform == key[0], Account.external_id == key[1]))
        await session.commit()


#Защита от дублей


def contact_keys(contact: str) -> set[str]:
    """Контакт → набор ключей для сравнения: @ники, e-mail, телефон (только цифры, 8 → 7)."""
    text = (contact or "").lower()
    keys = {f"email:{m}" for m in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)}
    without_emails = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", " ", text)
    keys |= {f"nick:{m}" for m in re.findall(r"@([a-z0-9_]{3,32})", without_emails)}
    digits = re.sub(r"\D", "", without_emails)
    if 10 <= len(digits) <= 12:
        if len(digits) == 11 and digits[0] == "8":
            digits = "7" + digits[1:]
        if len(digits) == 10:
            digits = "7" + digits
        keys.add(f"phone:{digits}")
    return keys


async def find_duplicate(account_id: str, contact: str) -> dict | None:
    """Анкета из ДРУГОГО мессенджера с тем же контактом — вероятно, тот же человек.

    Контакт пользователь вводит сам, поэтому это подсказка, а не доказательство:
    объединяем анкеты только по коду привязки, который видит лишь владелец.
    """
    keys = contact_keys(contact)
    platform = ids.platform_of(account_id)
    if not keys or platform not in ("tg", "max"):
        return None
    async with Session() as session:
        rows = list(await session.scalars(select(Profile).where(Profile.is_test.is_(False))))
    for profile in rows:
        if profile.user_id == str(account_id) or not (contact_keys(profile.username) & keys):
            continue
        if platform in await profile_platforms(profile.user_id):
            continue
        return profile.to_dict()
    return None


#Профили

async def get_profile(user_id: str | int) -> dict | None:
    """Анкета пользователя в формате Миши или None, если анкеты нет."""
    pid = await resolve_id(user_id)
    async with Session() as session:
        profile = await session.get(Profile, pid)
        return profile.to_dict() if profile else None

async def has_profile(user_id: str | int) -> bool:
    return await get_profile(user_id) is not None

async def save_profile(user_id: str | int, data: dict) -> dict:
    """Создаёт или обновляет анкету. data — словарь с полями Profile.

    interests должны быть уже нормализованы (core/interests.py).
    При создании анкеты в журнал согласий пишется действующая редакция согласия.
    """
    allowed = {
        "name", "university", "degree", "course", "direction", "city", "role", "looking_for",
        "interests", "about", "github", "username", "photo",
    }
    clean = {k: v for k, v in data.items() if k in allowed}
    pid = await resolve_id(user_id)
    async with Session() as session:
        profile = await session.get(Profile, pid)
        if profile is None:
            profile = Profile(user_id=pid, consent_at=datetime.now(timezone.utc), **clean)
            session.add(profile)
            session.add(Consent(profile_id=pid, account_id=str(user_id), version=settings.consent_version))
        else:
            for key, value in clean.items():
                setattr(profile, key, value)
        await session.commit()
        return profile.to_dict()

async def record_consent(user_id: str | int) -> None:
    """Повторное согласие (например, на новую редакцию документа) — дописать в журнал."""
    pid = await resolve_id(user_id)
    async with Session() as session:
        session.add(Consent(profile_id=pid, account_id=str(user_id), version=settings.consent_version))
        await session.commit()

async def set_active(user_id: str | int, is_active: bool) -> None:
    """Скрыть/показать анкету в ленте других пользователей."""
    pid = await resolve_id(user_id)
    async with Session() as session:
        profile = await session.get(Profile, pid)
        if profile:
            profile.is_active = is_active
            await session.commit()


async def delete_profile(user_id: str | int) -> None:
    """Удалить анкету, свайпы, настройки, привязки и журнал согласий (152-ФЗ, ст. 21).

    Анкета общая для всех мессенджеров, поэтому удаляется везде сразу.
    """
    pid = await resolve_id(user_id)
    async with Session() as session:
        profile = await session.get(Profile, pid)
        if profile:
            await session.delete(profile)
        await session.execute(delete(Swipe).where(or_(Swipe.from_id == pid, Swipe.to_id == pid)))
        await session.execute(delete(UserSettings).where(UserSettings.user_id == pid))
        await session.execute(delete(Account).where(Account.profile_id == pid))
        await session.execute(delete(LinkCode).where(LinkCode.profile_id == pid))
        await session.execute(delete(Consent).where(Consent.profile_id == pid))
        await session.commit()


async def list_active_profiles() -> list[dict]:
    """Все видимые анкеты — вход для core.recommendations.build_feed().

    Для MVP грузим всех в память: при сотнях анкет это быстро.
    При масштабировании — фильтровать по looking_for/интересам прямо в SQL.
    """
    async with Session() as session:
        rows = await session.scalars(select(Profile).where(Profile.is_active.is_(True)))
        return [p.to_dict() for p in rows]

#Свайпы, лайки, мэтчи
# from_id — всегда «я» (приводим к анкете), to_id — уже id анкеты из ленты.

async def save_swipe(from_id: str | int, to_id: str | int, liked: bool, message: str = "") -> None:
    """Записывает лайк (liked=True) или пропуск (liked=False). Повторный свайп перезаписывает старый."""
    me, other = await resolve_id(from_id), await resolve_id(to_id)
    async with Session() as session:
        existing = await session.scalar(
            select(Swipe).where(Swipe.from_id == me, Swipe.to_id == other)
        )
        if existing:
            existing.liked = liked
            existing.message = message
        else:
            session.add(Swipe(from_id=me, to_id=other, liked=liked, message=message))
        await session.commit()

async def get_swiped_ids(user_id: str | int) -> set[str]:
    """Кого пользователь уже оценил (лайк или пропуск) — их не показываем в ленте."""
    pid = await resolve_id(user_id)
    async with Session() as session:
        rows = await session.scalars(select(Swipe.to_id).where(Swipe.from_id == pid))
        return set(rows)

async def count_skips(user_id: str | int) -> int:
    """Сколько анкет пользователь пропустил (дизлайкнул)."""
    pid = await resolve_id(user_id)
    async with Session() as session:
        return await session.scalar(
            select(func.count()).select_from(Swipe).where(Swipe.from_id == pid, Swipe.liked.is_(False))
        ) or 0

async def reset_skips(user_id: str | int) -> None:
    """Забыть пропуски пользователя — пропущенные анкеты снова появятся в его ленте.

    Лайки не трогаем: лайкнутых повторно не показываем, их ответ (мэтч) ещё может прийти.
    """
    pid = await resolve_id(user_id)
    async with Session() as session:
        await session.execute(delete(Swipe).where(Swipe.from_id == pid, Swipe.liked.is_(False)))
        await session.commit()


async def get_likes_involving(user_id: str | int) -> list[dict]:
    """Все лайки, где участвует пользователь, в формате Миши: [{"from_id", "to_id", "message"}].

    Передаётся в core.interactions: is_match(), matches_for(), incoming_likes().
    Сравнивать их нужно с id анкеты — resolve_id(), а не с id аккаунта.
    """
    uid = await resolve_id(user_id)
    async with Session() as session:
        rows = await session.scalars(
            select(Swipe).where(Swipe.liked.is_(True), or_(Swipe.from_id == uid, Swipe.to_id == uid))
        )
        return [s.to_like_dict() for s in rows]


#Настройки поиска

SEARCH_MODES = ("all", "university", "city")


async def get_search_mode(user_id: str | int) -> str:
    """Режим ленты: all / university / city. По умолчанию — all."""
    pid = await resolve_id(user_id)
    async with Session() as session:
        row = await session.get(UserSettings, pid)
        return row.search_mode if row and row.search_mode in SEARCH_MODES else "all"


async def set_search_mode(user_id: str | int, mode: str) -> str:
    mode = mode if mode in SEARCH_MODES else "all"
    pid = await resolve_id(user_id)
    async with Session() as session:
        row = await session.get(UserSettings, pid)
        if row is None:
            session.add(UserSettings(user_id=pid, search_mode=mode))
        else:
            row.search_mode = mode
        await session.commit()
    return mode


# Мероприятия и цель поиска


async def list_events(include_past: bool = False) -> list[dict]:
    """Опубликованные мероприятия с числом тех, кто ищет на них команду.

    По умолчанию скрывает те, у которых прошёл и дедлайн, и дата начала:
    в ленте мёртвые анонсы только мешают.
    """
    today = datetime.now(timezone.utc).date()
    async with Session() as session:
        rows = (
            await session.execute(
                select(Event).where(Event.is_published).order_by(
                    Event.deadline_on.is_(None), Event.deadline_on, Event.starts_on
                )
            )
        ).scalars().all()
        counts = dict(
            (
                await session.execute(
                    select(ProfileEvent.event_id, func.count())
                    .where(ProfileEvent.event_id.is_not(None))
                    .group_by(ProfileEvent.event_id)
                )
            ).all()
        )
    out = []
    for ev in rows:
        last_day = ev.starts_on or ev.deadline_on
        if not include_past and last_day and last_day < today:
            continue
        out.append(ev.to_dict(seekers=int(counts.get(ev.id, 0))))
    return out


async def get_event(event_id: int | None) -> dict | None:
    if not event_id:
        return None
    async with Session() as session:
        ev = await session.get(Event, int(event_id))
        if not ev or not ev.is_published:
            return None
        seekers = await session.scalar(
            select(func.count()).select_from(ProfileEvent).where(ProfileEvent.event_id == ev.id)
        )
    return ev.to_dict(seekers=int(seekers or 0))


async def get_target_event(user_id: str | int) -> int | None:
    """id мероприятия, на которое человек ищет команду; None — ищет без цели."""
    pid = await resolve_id(user_id)
    async with Session() as session:
        row = await session.get(ProfileEvent, pid)
        return row.event_id if row else None


async def set_target_event(user_id: str | int, event_id: int | None) -> int | None:
    """Ставит или снимает цель поиска. Несуществующее мероприятие трактуем как «без цели»."""
    pid = await resolve_id(user_id)
    event_id = int(event_id) if event_id else None
    async with Session() as session:
        if event_id is not None:
            ev = await session.get(Event, event_id)
            if not ev or not ev.is_published:
                event_id = None
        row = await session.get(ProfileEvent, pid)
        if row:
            row.event_id = event_id
        else:
            session.add(ProfileEvent(profile_id=pid, event_id=event_id))
        await session.commit()
    return event_id


async def ids_targeting(event_id: int) -> set[str]:
    """Кто ищет команду на это мероприятие."""
    async with Session() as session:
        rows = (
            await session.execute(
                select(ProfileEvent.profile_id).where(ProfileEvent.event_id == int(event_id))
            )
        ).scalars().all()
    return set(rows)

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Profile(Base):
    """Анкета пользователя. Одна строка = один человек."""

    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    university: Mapped[str] = mapped_column(String(100), default="")

    degree: Mapped[str] = mapped_column(String(40), default="")
    course: Mapped[int | None] = mapped_column(Integer, nullable=True)
    direction: Mapped[str] = mapped_column(String(100), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(50))
    looking_for: Mapped[str] = mapped_column(String(50))
    interests: Mapped[list] = mapped_column(JSON, default=list)
    about: Mapped[str] = mapped_column(Text, default="")
    github: Mapped[str] = mapped_column(String(200), default="")
    
    username: Mapped[str] = mapped_column(String(100), default="")
    photo: Mapped[str] = mapped_column(String(500), default="")

    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> dict:
        """Профиль в формате Миши (словарь) — для core/matching.py и core/recommendations.py."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "name": self.name,
            "university": self.university,
            "degree": self.degree,
            "course": self.course,
            "direction": self.direction,
            "city": self.city,
            "role": self.role,
            "looking_for": self.looking_for,
            "interests": list(self.interests or []),
            "about": self.about,
            "github": self.github,
            "photo": self.photo,
            "is_test": self.is_test,
            "is_active": self.is_active,
        }

class Swipe(Base):
    """Одна оценка анкеты: кто (from_id) кого (to_id) лайкнул или пропустил.

    Дизлайки тоже храним — чтобы не показывать человека повторно.
    Лайки (liked=True) превращаются в формат Миши через Swipe.to_like_dict().
    """

    __tablename__ = "swipes"
    __table_args__ = (UniqueConstraint("from_id", "to_id", name="uq_swipe_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_id: Mapped[str] = mapped_column(String(64), index=True)
    to_id: Mapped[str] = mapped_column(String(64), index=True)
    liked: Mapped[bool] = mapped_column(Boolean)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def to_like_dict(self) -> dict:
        """Лайк в формате core/interactions.py: {"from_id", "to_id", "message"}."""
        return {"from_id": self.from_id, "to_id": self.to_id, "message": self.message}


class UserSettings(Base):
    """Настройки пользователя, которые должны переживать перезапуск.

    Отдельная таблица, а не колонка в profiles: create_all создаёт новые таблицы
    на боевой базе, но не добавляет колонки в существующие.
    """

    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    search_mode: Mapped[str] = mapped_column(String(20), default="all")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Account(Base):
    """Аккаунт мессенджера, привязанный к чужой (уже существующей) анкете.

    Анкета одна на человека. Её id — id аккаунта, с которого её создали
    (MAX: «123», Telegram: «tg:123»). Если тот же человек подключает второй мессенджер,
    сюда пишется строка «платформа + внешний id → id анкеты», и второй аккаунт
    видит и правит ту же анкету. Для первого (родного) аккаунта строка не нужна.
    """

    __tablename__ = "accounts"

    platform: Mapped[str] = mapped_column(String(10), primary_key=True)      # tg / max
    external_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LinkCode(Base):
    """Одноразовый код привязки второго мессенджера. Живёт 10 минут."""

    __tablename__ = "link_codes"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Consent(Base):
    """Журнал согласий на обработку ПД (152-ФЗ, ст. 9): кто, когда, с какой площадки, какую редакцию."""

    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    account_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(20))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Event(Base):
    """Мероприятие: хакатон, кейс-чемпионат, олимпиада.

    Заполняется руками через tools/, а не парсером: для пилота релевантных
    событий два-пять в месяц, а поля «организатор» и «кто отвечает за бюджет»
    парсер всё равно не достанет — их добывают в переписке.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    organizer: Mapped[str] = mapped_column(String(120), default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    format: Mapped[str] = mapped_column(String(40), default="")      # очно / онлайн / гибрид
    team_size: Mapped[str] = mapped_column(String(20), default="")   # «3–5» — строкой, для показа
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    about: Mapped[str] = mapped_column(Text, default="")
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self, seekers: int = 0) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "organizer": self.organizer,
            "url": self.url,
            "city": self.city,
            "format": self.format,
            "team_size": self.team_size,
            "starts_on": self.starts_on.isoformat() if self.starts_on else None,
            "deadline_on": self.deadline_on.isoformat() if self.deadline_on else None,
            "about": self.about,
            "seekers": seekers,
        }


class ProfileEvent(Base):
    """На какое мероприятие человек сейчас ищет команду. Пусто — ищет без цели.

    Отдельная таблица, а не колонка в profiles: create_all создаёт новые таблицы
    на боевой базе, но не добавляет колонки в существующие.
    """

    __tablename__ = "profile_events"

    profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

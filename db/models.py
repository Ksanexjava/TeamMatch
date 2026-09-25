# db/models.py
# Таблицы базы данных (зона Романа).
# Поля профиля совпадают с форматом Миши из core/matching.py и data/test_profiles.json,
# поэтому Profile.to_dict() можно сразу отдавать в build_feed() / compatibility().

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Profile(Base):
    """Анкета пользователя. Одна строка = один человек."""

    __tablename__ = "profiles"

    # user_id храним строкой: у реальных пользователей MAX это число ("12345678"),
    # у тестовых анкет — "u001". Так формат одинаковый для всех.
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    university: Mapped[str] = mapped_column(String(100), default="")
    course: Mapped[int | None] = mapped_column(Integer, nullable=True)
    city: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(50))
    looking_for: Mapped[str] = mapped_column(String(50))
    interests: Mapped[list] = mapped_column(JSON, default=list)   # уже нормализованные
    about: Mapped[str] = mapped_column(Text, default="")
    github: Mapped[str] = mapped_column(String(200), default="")
    # Контакт для связи после мэтча (ник в MAX, телефон, ссылка — что указал человек)
    username: Mapped[str] = mapped_column(String(100), default="")
    photo: Mapped[str] = mapped_column(String(500), default="")  # токен фото в MAX (или пусто)

    is_test: Mapped[bool] = mapped_column(Boolean, default=False)  # тестовые анкеты из JSON
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # скрыть анкету из ленты
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
            "course": self.course,
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

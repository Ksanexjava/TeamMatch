"""Сценарий Telegram-бота целиком — без сети.

Настоящие апдейты Telegram прогоняются через диспетчер бота, а вместо HTTP-сессии
стоит FakeSession: она запоминает, что бот отправил, и возвращает правдоподобный ответ.
"""

import asyncio
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage, SendPhoto
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from db import repo
from db.session import init_db
from tgbot.main import build_dispatcher

BOT_USER = User(id=42, is_bot=True, first_name="Тиммейт", username="teammate_test_bot")


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls: list = []
        self._id = 1000

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, SendPhoto)):
            self._id += 1
            return Message(
                message_id=self._id, date=datetime.now(timezone.utc),
                chat=Chat(id=method.chat_id, type="private"), from_user=BOT_USER,
                text=getattr(method, "text", None), caption=getattr(method, "caption", None),
                reply_markup=method.reply_markup,
            )
        return True

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""


_DP = None


def _dispatcher():
    """Роутер aiogram подключается только к одному диспетчеру — делим его между пользователями."""
    global _DP
    if _DP is None:
        _DP = build_dispatcher()
    return _DP


class Chatter:
    """Один пользователь Telegram, который пишет боту и жмёт кнопки."""

    def __init__(self, user_id: int, username: str = ""):
        self.user = User(id=user_id, is_bot=False, first_name="Тест", username=username or None)
        self.session = FakeSession()
        self.bot = Bot(token="42:TEST", session=self.session)
        self.dp = _dispatcher()
        self._n = 0

    def _upd(self, **kw) -> Update:
        self._n += 1
        return Update(update_id=self._n, **kw)

    async def say(self, text: str):
        msg = Message(message_id=self._n + 1, date=datetime.now(timezone.utc),
                      chat=Chat(id=self.user.id, type="private"), from_user=self.user, text=text)
        await self.dp.feed_update(self.bot, self._upd(message=msg))

    async def press(self, data: str):
        msg = Message(message_id=self.session._id, date=datetime.now(timezone.utc),
                      chat=Chat(id=self.user.id, type="private"), from_user=BOT_USER, text="…")
        cb = CallbackQuery(id=str(self._n), from_user=self.user, chat_instance="x", data=data, message=msg)
        await self.dp.feed_update(self.bot, self._upd(callback_query=cb))

    def sent(self) -> list:
        return [c for c in self.session.calls if isinstance(c, (SendMessage, SendPhoto))]

    def last_sent(self):
        s = self.sent()
        return s[-1] if s else None

    def last_text(self) -> str:
        m = self.last_sent()
        return (getattr(m, "text", None) or getattr(m, "caption", None) or "") if m else ""

    def buttons(self) -> list[str]:
        m = self.last_sent()
        if not m or not m.reply_markup:
            return []
        return [b.callback_data for row in m.reply_markup.inline_keyboard for b in row if b.callback_data]


async def fill_form(c: Chatter, contact: str) -> None:
    await c.press("consent:yes")
    assert "Как тебя зовут" in c.last_text()
    await c.say("Лёша")
    await c.press("form:skip")                 # фото
    await c.say("заходи на site.ru")            # реклама в поле вуза
    assert "Ссылки здесь нельзя" in c.last_text()
    await c.say("НГУ")
    await c.press("deg:1")                      # магистратура
    assert c.buttons() == ["course:1", "course:2"]
    await c.press("course:1")
    await c.say("Экономика")
    await c.say("Новосибирск")
    await c.press("role:5")                     # финансы
    await c.press("goal:1")                     # кейс-чемпионат
    await c.say("python, аналитика, питон")
    await c.press("form:skip")                  # о себе
    await c.press("form:skip")                  # GitHub
    await c.say(contact)
    assert "Проверь анкету" in c.last_text()
    await c.press("form:save")


def run(coro):
    return asyncio.run(coro)


def test_full_scenario_in_telegram():
    async def scenario():
        await init_db()
        c = Chatter(9001, username="lesha_tg")
        await c.say("/start")
        assert "152-ФЗ" in c.last_text()
        assert "consent:yes" in c.buttons() and "link:start" in c.buttons()

        await fill_form(c, "@lesha_tg")
        assert "Главное меню" in c.last_text()
        profile = await repo.get_profile("tg:9001")
        assert profile["degree"] == "магистратура" and profile["course"] == 1
        assert profile["role"] == "финансы" and profile["interests"] == ["python", "аналитика"]

        # Лента и лайк тестовой анкеты → мэтч с контактом
        await c.press("menu:feed")
        like = next(b for b in c.buttons() if b.startswith("feed:like:"))
        await c.press(like)
        assert "новый мэтч" in c.last_text() and "Контакт" in c.last_text()

        # Пропуск → следующая анкета
        await c.press("feed:next")
        skip = next(b for b in c.buttons() if b.startswith("feed:skip:"))
        await c.press(skip)
        assert any(b.startswith("feed:like:") for b in c.buttons())

        await c.press("menu:matches")
        assert any("Твои мэтчи" in (getattr(m, "text", "") or "") for m in c.session.calls if hasattr(m, "text"))

        # Точечная правка поля
        await c.press("edit:city")
        await c.say("Томск")
        assert (await repo.get_profile("tg:9001"))["city"] == "Томск"

    run(scenario())


def test_link_telegram_to_max_profile_by_code():
    async def scenario():
        await init_db()
        await repo.save_profile("7700", {
            "name": "Аня", "university": "НГУ", "role": "дизайн", "looking_for": "хакатон",
            "interests": ["figma"], "username": "@anya_max",
        })
        code, _ = await repo.create_link_code("7700")
        c = Chatter(9002)
        await c.say(f"/link {code}")
        assert "Telegram подключён" in " ".join(
            (getattr(m, "text", "") or "") for m in c.sent())
        assert await repo.resolve_id("tg:9002") == "7700"

        # Ссылка из бота MAX: /start link-<код>
        code2, _ = await repo.create_link_code("7700")
        c2 = Chatter(9003)
        await c2.say(f"/start link-{code2}")
        assert "уже подключён другой аккаунт Telegram" in c2.last_text()

    run(scenario())


def test_duplicate_contact_warns_before_second_profile():
    async def scenario():
        await init_db()
        await repo.save_profile("7800", {
            "name": "Лёша", "university": "НГУ", "role": "финансы", "looking_for": "хакатон",
            "interests": ["python"], "username": "@lesha_dup",
        })
        c = Chatter(9004)
        await c.say("/start")
        await fill_form(c, "ТГ: @Lesha_Dup")
        assert "уже есть анкета в MAX" in c.last_text()
        assert await repo.get_profile("tg:9004") is None
        await c.press("form:save_force")
        assert await repo.get_profile("tg:9004") is not None

    run(scenario())

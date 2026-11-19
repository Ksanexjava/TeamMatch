"""Сценарий Telegram-бота целиком — без сети.

Настоящие апдейты Telegram прогоняются через диспетчер бота, а вместо HTTP-сессии
стоит FakeSession: она запоминает, что бот отправил, и возвращает правдоподобный ответ.
"""

import asyncio
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageReplyMarkup, EditMessageText, GetMe, SendMessage, SendPhoto
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from db import repo
from db.session import init_db
from tgbot.main import build_dispatcher
from tgbot.ui import attach_bot

BOT_USER = User(id=42, is_bot=True, first_name="Тиммейт", username="teammate_test_bot")


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls: list = []
        self._id = 1000

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, GetMe):
            return BOT_USER
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
        attach_bot(self.bot, self.dp)
        self._n = 0

    def _upd(self, **kw) -> Update:
        self._n += 1
        return Update(update_id=self._n, **kw)

    async def say(self, text: str):
        msg = Message(message_id=self._n + 1, date=datetime.now(timezone.utc),
                      chat=Chat(id=self.user.id, type="private"), from_user=self.user, text=text)
        await self.dp.feed_update(self.bot, self._upd(message=msg))

    async def press(self, data: str, message_id: int | None = None):
        msg = Message(message_id=message_id or self.session._id, date=datetime.now(timezone.utc),
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


def texts_of(c: "Chatter") -> list[str]:
    """Всё, что бот отправил или во что отредактировал сообщения."""
    out = []
    for m in c.session.calls:
        if isinstance(m, (SendMessage, EditMessageText)):
            out.append(m.text or "")
        elif isinstance(m, SendPhoto):
            out.append(m.caption or "")
    return out


def test_events_in_telegram():
    async def scenario():
        await init_db()
        ev = await repo.create_event({"title": "Тест-хакатон", "starts_on": "2027-01-20", "deadline_on": "2027-01-10",
                                      "format": "онлайн", "team_size": "3–5", "url": "https://example.com/hack"})
        ev2 = await repo.create_event({"title": "Кейс-чемп", "deadline_on": "2027-02-01"})

        # Новичок приходит по ссылке из анонса: цель ставится сразу после анкеты
        c = Chatter(9101, username="anya_events")
        await c.say(f"/start event-{ev['id']}")
        assert any("подберу людей на «Тест-хакатон»" in t for t in texts_of(c))
        await fill_form(c, "@anya_events")
        assert "Цель: Тест-хакатон" in c.last_text()
        assert await repo.get_target_event("tg:9101") == ev["id"]

        # На мероприятие больше никто не ищет — заглушка со ссылкой-приглашением
        await c.press("menu:feed")
        assert "пока никто, кроме тебя" in c.last_text()
        assert f"t.me/teammate_test_bot?start=event-{ev['id']}" in c.last_text()

        # Второй человек выбирает то же мероприятие через список
        d = Chatter(9102, username="dima_events")
        await d.press("consent:yes")
        await fill_form(d, "@dima_events")
        await d.press("menu:events")
        assert "Тест-хакатон" in d.last_text() and "Ищут команду: 1" in d.last_text()
        assert f"ev:pick:{ev2['id']}" in d.buttons()
        await d.press(f"ev:pick:{ev['id']}")
        assert await repo.get_target_event("tg:9102") == ev["id"]

        # Теперь у первого в ленте только он — с пометкой цели
        await c.press("menu:feed")
        assert c.last_text().startswith("🎯 Тест-хакатон") and "Лёша" in c.last_text()

        # Входящий лайк виден в главном меню; после мэтча есть «Написать» в Telegram
        like = next(b for b in c.buttons() if b.startswith("feed:like:"))
        await c.press(like)
        await d.press("menu:back")
        assert any("Тебя лайкнули: 1" in t for t in texts_of(d))
        await d.press("menu:feed")
        await d.press(next(b for b in d.buttons() if b.startswith("feed:like:")))
        assert "новый мэтч" in d.last_text()
        urls = [b.url for row in d.last_sent().reply_markup.inline_keyboard for b in row if b.url]
        assert "https://t.me/anya_events" in urls

        # Снять цель
        await d.press("ev:clear")
        assert await repo.get_target_event("tg:9102") is None

        # Удаление анкеты стирает и цель поиска — удалённый не висит в счётчике
        await repo.delete_profile("tg:9101")
        assert "tg:9101" not in await repo.ids_targeting(ev["id"])

    run(scenario())


def test_event_link_to_unknown_event():
    async def scenario():
        await init_db()
        c = Chatter(9103)
        await c.say("/start event-999999")
        assert any("уже прошло или снято" in t for t in texts_of(c))
        assert "152-ФЗ" in c.last_text()  # дальше — обычное приветствие

    run(scenario())


def test_only_latest_message_keeps_buttons():
    async def scenario():
        await init_db()
        c = Chatter(9201, username="lag_user")
        await c.say("/start")
        await fill_form(c, "@lag_user")
        first_menu = c.session._id

        # Двойной /start (лаг сети): у первого меню кнопки снимаются
        await c.say("/start")
        second_menu = c.session._id
        assert second_menu > first_menu
        dropped = [m for m in c.session.calls if isinstance(m, EditMessageReplyMarkup) and m.reply_markup is None]
        assert any(m.message_id == first_menu for m in dropped)

        # Нажатие на старое меню не выполняется: «меню устарело», новых сообщений нет
        sent_before = len(c.sent())
        await c.press("menu:feed", message_id=first_menu)
        assert len(c.sent()) == sent_before
        answers = [m for m in c.session.calls if isinstance(m, AnswerCallbackQuery)]
        assert "устарело" in (answers[-1].text or "")

        # Двойной тап по актуальному меню: выполняется один раз
        sent_before = len(c.sent())
        await asyncio.gather(c.press("menu:feed", message_id=second_menu), c.press("menu:feed", message_id=second_menu))
        assert len(c.sent()) == sent_before + 1

    run(scenario())

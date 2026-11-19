"""Сценарий Telegram-бота — тот же, что у бота MAX (bot/handlers/*), но на aiogram.

Пользователь Telegram в общей базе — «tg:<id>» (messengers/ids.py). Все функции db/repo.py
сами приводят id аккаунта к id анкеты, поэтому аккаунт, подключённый к анкете из MAX,
работает с той же анкетой, лентой, лайками и мэтчами.
"""

import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User

from bot import keyboards as max_kb
from bot import media as max_media
from bot.keyboards import DEGREES, MED_DEGREES, ROLES
from config import settings
from core.interactions import incoming_likes, is_match, matches_for
from core.interests import LOOKING_FOR_OPTIONS, normalize_interests
from core.moderation import has_ads, is_clean, is_valid_contact, normalize_github
from core.recommendations import build_feed, explain
from db import repo
from messengers import ids, notify
from tgbot import keyboards as kb
from tgbot import texts
from tgbot.states import FeedFlow, Form, LinkFlow

log = logging.getLogger(__name__)
router = Router(name="teammate")

LIMITS = {
    "name": 50, "university": 100, "course": 2, "direction": 100, "city": 60,
    "about": 500, "github": 200, "username": 100,
}
CAPTION_LIMIT = 1024  # подпись к фото в Telegram


def uid(user: User) -> str:
    """id аккаунта Telegram в общем пуле анкет."""
    return ids.from_telegram(user.id)


# ---------------------------------------------------------------- отправка

async def send(bot: Bot, chat_id: int, text: str, markup: InlineKeyboardMarkup | None = None,
               profile: dict | None = None) -> None:
    """Сообщение; если у анкеты есть фото из Telegram — фото с подписью."""
    photo = (profile or {}).get("photo") or ""
    if photo.startswith("tgfile:"):
        try:
            # Одним сообщением: второе сообщение-«хвост» забрало бы у карточки кнопки.
            caption = text if len(text) <= CAPTION_LIMIT else text[:CAPTION_LIMIT - 1] + "…"
            await bot.send_photo(chat_id, photo[len("tgfile:"):], caption=caption, reply_markup=markup)
            return
        except TelegramBadRequest:
            pass  # фото удалено или недоступно — покажем текстом
    await bot.send_message(chat_id, text, reply_markup=markup)


async def show(cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Заменить текст сообщения с кнопкой; если нельзя (фото, старое) — прислать новое."""
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except (TelegramBadRequest, AttributeError):
        await drop_buttons(cb)
        await cb.bot.send_message(cb.from_user.id, text, reply_markup=markup)


async def drop_buttons(cb: CallbackQuery) -> None:
    """Убрать кнопки со старого сообщения, оставив его содержимое."""
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except (TelegramBadRequest, AttributeError):
        pass


# ---------------------------------------------------------------- старт и меню

async def menu_text(account_id: str) -> str:
    """Главное меню + входящие лайки и текущая цель — как плашки в мини-приложении."""
    lines = [texts.MAIN_MENU]
    me = await repo.resolve_id(account_id)
    likes = await repo.get_likes_involving(me)
    n = len(incoming_likes(likes, me, await repo.get_swiped_ids(me)))
    if n:
        lines.append(texts.MENU_INCOMING.format(n=n))
    event = await repo.get_event(await repo.get_target_event(me))
    if event:
        lines.append(texts.MENU_TARGET.format(title=event["title"]))
    return "\n\n".join(lines)


async def send_menu(bot: Bot, user: User) -> None:
    await bot.send_message(user.id, await menu_text(uid(user)), reply_markup=kb.main_menu_kb())


async def greet(bot: Bot, user: User) -> None:
    if await repo.has_profile(uid(user)):
        await send_menu(bot, user)
    else:
        await bot.send_message(user.id, texts.WELCOME, reply_markup=kb.consent_kb())


@router.message(CommandStart())
async def on_start(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()
    payload = command.args or ""
    if payload.startswith("event-"):
        # https://t.me/<бот>?start=event-<id> — кнопка «Найти команду» под анонсом
        await start_with_event(message.bot, message.from_user, payload[len("event-"):], state)
        return
    if payload.startswith("link-"):
        # https://t.me/<бот>?start=link-<код> — кнопка «Открыть в Telegram» из бота MAX
        await redeem(message.bot, message.from_user, payload[len("link-"):], state)
        return
    await greet(message.bot, message.from_user)


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(texts.HELP)


@router.message(Command("cancel"))
async def on_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer(texts.NOTHING_TO_CANCEL)
        return
    await state.clear()
    await message.answer(texts.CANCELLED)


@router.message(Command("report"))
async def cmd_report(message: Message) -> None:
    await message.answer(texts.REPORT, reply_markup=kb.back_kb())


@router.callback_query(F.data == kb.MENU_REPORT)
async def on_report(cb: CallbackQuery) -> None:
    await cb.answer()
    await show(cb, texts.REPORT, kb.back_kb())


@router.callback_query(F.data == kb.MENU_BACK)
async def on_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.clear()
    await show(cb, await menu_text(uid(cb.from_user)), kb.main_menu_kb())


@router.callback_query(F.data == kb.MENU_START)
async def on_menu_start(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.clear()
    await drop_buttons(cb)
    await greet(cb.bot, cb.from_user)


@router.callback_query(F.data == kb.CONSENT_YES)
async def on_consent_yes(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    await start_form(cb.bot, cb.from_user, state)


@router.callback_query(F.data == kb.CONSENT_NO)
async def on_consent_no(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.clear()
    await show(cb, texts.CONSENT_DECLINED)


# ---------------------------------------------------------------- анкета

# Шаг → следующий шаг (как в боте MAX). degree → course обрабатывается в кнопках.
NEXT = {
    "name": "photo", "photo": "university", "university": "degree", "course": "direction",
    "direction": "city", "city": "role", "role": "looking_for", "looking_for": "interests",
    "interests": "about", "about": "github", "github": "username", "username": "confirm",
}
TEXT_FIELDS = {"name", "university", "direction", "city", "about", "github", "username"}


async def start_form(bot: Bot, user: User, state: FSMContext) -> None:
    pending = (await state.get_data()).get("pending_event")  # пришёл по ссылке мероприятия
    await state.clear()
    await state.update_data(tg_username=user.username or "", first_name=user.first_name or "", pending_event=pending)
    await ask(bot, user.id, "name", state)


async def ask(bot: Bot, chat_id: int, field: str, state: FSMContext) -> None:
    data = await state.get_data()
    prompts = {
        "name": (texts.ASK_NAME, None),
        "photo": (texts.ASK_PHOTO, kb.skip_kb()),
        "university": (texts.ASK_UNIVERSITY, None),
        "degree": (texts.ASK_DEGREE, kb.degree_kb()),
        "direction": (texts.ASK_DIRECTION, None),
        "city": (texts.ASK_CITY, None),
        "role": (texts.ASK_ROLE, kb.role_kb()),
        "looking_for": (texts.ASK_LOOKING_FOR, kb.looking_for_kb()),
        "interests": (texts.ASK_INTERESTS, None),
        "about": (texts.ASK_ABOUT, kb.skip_kb()),
        "github": (texts.ASK_GITHUB, kb.skip_kb()),
        "username": (texts.ASK_CONTACT, kb.contact_kb(data.get("tg_username"))),
    }
    text, markup = prompts[field]
    await state.set_state(getattr(Form, field))
    await bot.send_message(chat_id, text, reply_markup=markup)


async def advance(bot: Bot, chat_id: int, state: FSMContext, done: str) -> None:
    """Следующий шаг анкеты — или, если это точечное редактирование, сохранить и показать анкету."""
    data = await state.get_data()
    if data.get("edit_last") == done:
        await repo.save_profile(data["edit_user_id"], data)
        await state.clear()
        await bot.send_message(chat_id, texts.EDIT_SAVED)
        await send_profile(bot, chat_id, data["edit_user_id"])
        return
    nxt = NEXT[done]
    if nxt == "confirm":
        await state.set_state(Form.confirm)
        card = texts.profile_card(data, show_contact=True)
        await send(bot, chat_id, f"Проверь анкету:\n\n{card}", kb.confirm_kb(), data)
    else:
        await ask(bot, chat_id, nxt, state)


async def take_text(message: Message, field: str) -> str | None:
    """Проверка ответа: не пусто, лимит длины, без мата и рекламы. None — переспросить."""
    value = (message.text or "").strip()
    if not value:
        await message.answer(texts.EMPTY_TEXT)
        return None
    limit = LIMITS.get(field, 200)
    if len(value) > limit:
        await message.answer(texts.TOO_LONG.format(limit=limit))
        return None
    if not is_clean(value):
        await message.answer(texts.BANNED_WORDS)
        return None
    if field == "github":
        github = normalize_github(value)
        if github is None:
            await message.answer(texts.BAD_GITHUB, reply_markup=kb.skip_kb())
            return None
        return github
    if field == "username":
        if not is_valid_contact(value):
            await message.answer(texts.BAD_CONTACT)
            return None
        return value
    if has_ads(value):
        await message.answer(texts.NO_LINKS)
        return None
    return value


@router.message(StateFilter(Form.name, Form.university, Form.direction, Form.city, Form.about,
                            Form.github, Form.username), F.text)
async def step_text(message: Message, state: FSMContext) -> None:
    field = (await state.get_state()).split(":", 1)[1]
    value = await take_text(message, field)
    if value is None:
        return
    await state.update_data(**{field: value})
    await advance(message.bot, message.chat.id, state, field)


@router.message(Form.course_manual, F.text)
async def step_course_manual(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value.isdigit() or not 1 <= int(value) <= 10:
        await message.answer(texts.BAD_COURSE)
        return
    await state.update_data(course=int(value))
    await advance(message.bot, message.chat.id, state, "course")


@router.message(Form.interests, F.text)
async def step_interests(message: Message, state: FSMContext) -> None:
    raw = message.text or ""
    if not is_clean(raw):
        await message.answer(texts.BANNED_WORDS)
        return
    if has_ads(raw):
        await message.answer(texts.NO_LINKS)
        return
    interests = normalize_interests(raw)
    if not interests:
        await message.answer(texts.NO_INTERESTS)
        return
    await state.update_data(interests=interests)
    await advance(message.bot, message.chat.id, state, "interests")


@router.message(Form.photo, F.photo)
async def step_photo(message: Message, state: FSMContext) -> None:
    await state.update_data(photo="tgfile:" + message.photo[-1].file_id)
    await advance(message.bot, message.chat.id, state, "photo")


@router.message(Form.photo)
async def step_photo_other(message: Message) -> None:
    await message.answer(texts.NO_PHOTO_HINT, reply_markup=kb.skip_kb())


@router.callback_query(F.data == kb.FORM_SKIP)
async def step_skip(cb: CallbackQuery, state: FSMContext) -> None:
    """«Пропустить» на необязательных шагах: фото, о себе, GitHub."""
    await cb.answer()
    current = await state.get_state()
    field = current.split(":", 1)[1] if current else ""
    if field not in ("photo", "about", "github"):
        return
    await drop_buttons(cb)
    await state.update_data(**{field: ""})
    await advance(cb.bot, cb.from_user.id, state, field)


@router.callback_query(Form.degree, F.data.startswith("deg:"))
async def step_degree(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    choice = cb.data.split(":", 1)[1]
    if choice == "other":
        await state.set_state(Form.degree_med)
        await cb.bot.send_message(cb.from_user.id, texts.ASK_DEGREE_MED, reply_markup=kb.degree_med_kb())
        return
    label, value, max_courses = DEGREES[int(choice)]
    await state.update_data(degree=value)
    await state.set_state(Form.course)
    await cb.bot.send_message(cb.from_user.id, texts.ASK_COURSE, reply_markup=kb.course_kb(max_courses))


@router.callback_query(Form.degree_med, F.data.startswith("degmed:"))
async def step_degree_med(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    _, value, _ = MED_DEGREES[int(cb.data.split(":", 1)[1])]
    await state.update_data(degree=value)
    await state.set_state(Form.course_manual)
    await cb.bot.send_message(cb.from_user.id, texts.ASK_COURSE_MANUAL)


@router.callback_query(Form.course, F.data.startswith("course:"))
async def step_course(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    await state.update_data(course=int(cb.data.split(":", 1)[1]))
    await advance(cb.bot, cb.from_user.id, state, "course")


@router.callback_query(Form.role, F.data.startswith("role:"))
async def step_role(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    await state.update_data(role=ROLES[int(cb.data.split(":", 1)[1])])
    await advance(cb.bot, cb.from_user.id, state, "role")


@router.callback_query(Form.looking_for, F.data.startswith("goal:"))
async def step_goal(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    await state.update_data(looking_for=LOOKING_FOR_OPTIONS[int(cb.data.split(":", 1)[1])])
    await advance(cb.bot, cb.from_user.id, state, "looking_for")


@router.callback_query(Form.username, F.data == kb.FORM_USE_USERNAME)
async def step_use_username(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    data = await state.get_data()
    await state.update_data(username="@" + data.get("tg_username", ""))
    await advance(cb.bot, cb.from_user.id, state, "username")


@router.callback_query(Form.confirm, F.data == kb.FORM_SAVE)
async def step_save(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    me = uid(cb.from_user)
    data = await state.get_data()
    # Новая анкета с контактом, который уже есть у анкеты из MAX, — скорее всего, человек уже с нами.
    if not await repo.has_profile(me):
        duplicate = await repo.find_duplicate(me, data.get("username", ""))
        if duplicate:
            await drop_buttons(cb)
            await cb.bot.send_message(cb.from_user.id, texts.DUPLICATE_FOUND.format(contact=duplicate.get("username") or "—"),
                                      reply_markup=kb.duplicate_kb())
            return
    await save_new(cb, state)


@router.callback_query(Form.confirm, F.data == kb.FORM_SAVE_FORCE)
async def step_save_force(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await save_new(cb, state)


async def save_new(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    me = uid(cb.from_user)
    await repo.save_profile(me, data)
    await state.clear()
    await drop_buttons(cb)
    await cb.bot.send_message(cb.from_user.id, texts.PROFILE_SAVED)
    if data.get("pending_event") and await repo.set_target_event(me, data["pending_event"]):
        event = await repo.get_event(data["pending_event"])
        await cb.bot.send_message(cb.from_user.id, texts.EVENT_SET.format(title=event["title"]), reply_markup=kb.event_set_kb())
        return
    await send_menu(cb.bot, cb.from_user)


@router.callback_query(Form.confirm, F.data == kb.FORM_RESTART)
async def step_restart(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    await start_form(cb.bot, cb.from_user, state)


# ---------------------------------------------------------------- моя анкета

async def send_profile(bot: Bot, chat_id: int, account_id: str) -> None:
    profile = await repo.get_profile(account_id)
    if profile is None:
        await bot.send_message(chat_id, texts.NO_PROFILE)
        return
    card = texts.profile_card(profile, show_contact=True)
    if not profile.get("is_active", True):
        card += "\n\n🙈 Анкета скрыта из поиска."
    platforms = await repo.profile_platforms(profile["user_id"])
    await send(bot, chat_id, card, kb.profile_kb(profile.get("is_active", True), "max" in platforms), profile)


@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_profile(message.bot, message.chat.id, uid(message.from_user))


@router.callback_query(F.data == kb.MENU_PROFILE)
async def on_profile(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.clear()
    await drop_buttons(cb)
    await send_profile(cb.bot, cb.from_user.id, uid(cb.from_user))


@router.callback_query(F.data == kb.MENU_EDIT)
async def on_edit_all(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    await start_form(cb.bot, cb.from_user, state)


@router.callback_query(F.data == kb.MENU_EDIT_FIELDS)
async def on_edit_fields(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.clear()
    await show(cb, texts.EDIT_CHOOSE, kb.edit_fields_kb())


# Поле → (с какого шага начать, на каком закончить)
EDIT_STEPS = {
    "name": ("name", "name"), "photo": ("photo", "photo"), "university": ("university", "university"),
    "education": ("degree", "course"), "direction": ("direction", "direction"), "city": ("city", "city"),
    "role": ("role", "role"), "looking_for": ("looking_for", "looking_for"), "interests": ("interests", "interests"),
    "about": ("about", "about"), "github": ("github", "github"), "username": ("username", "username"),
}


@router.callback_query(F.data.startswith(kb.EDIT_FIELD + ":"))
async def on_edit_field(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    key = cb.data.split(":", 1)[1]
    if key not in EDIT_STEPS:
        return
    me = uid(cb.from_user)
    profile = await repo.get_profile(me)
    if profile is None:
        await show(cb, texts.NO_PROFILE)
        return
    first, last = EDIT_STEPS[key]
    await state.clear()
    await state.update_data(**profile, tg_username=cb.from_user.username or "", edit_user_id=me, edit_last=last)
    await drop_buttons(cb)
    await ask(cb.bot, cb.from_user.id, first, state)


@router.callback_query(F.data.in_({kb.MENU_HIDE, kb.MENU_SHOW}))
async def on_visibility(cb: CallbackQuery) -> None:
    active = cb.data == kb.MENU_SHOW
    await repo.set_active(uid(cb.from_user), active)
    await cb.answer(texts.PROFILE_SHOWN if active else "Анкета скрыта")
    await drop_buttons(cb)
    await send_profile(cb.bot, cb.from_user.id, uid(cb.from_user))


@router.callback_query(F.data == kb.MENU_DELETE)
async def on_delete(cb: CallbackQuery) -> None:
    await cb.answer()
    await drop_buttons(cb)
    await cb.bot.send_message(cb.from_user.id, texts.DELETE_ASK, reply_markup=kb.delete_confirm_kb())


@router.callback_query(F.data == kb.MENU_DELETE_CONFIRM)
async def on_delete_confirm(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await repo.delete_profile(uid(cb.from_user))
    await state.clear()
    await show(cb, texts.DELETED, kb.start_again_kb())


# ---------------------------------------------------------------- лента

def card_text(item: dict) -> str:
    return f"{texts.profile_card(item['profile'])}\n\n⚡ {explain(item['details'])}"


def filter_pool(me: dict, pool: list, mode: str) -> list:
    field = {"university": "university", "city": "city"}.get(mode)
    if not field:
        return pool
    key = (me.get(field) or "").strip().lower()
    return [p for p in pool if key and (p.get(field) or "").strip().lower() == key]


async def show_next(bot: Bot, chat_id: int, account_id: str) -> None:
    me = await repo.get_profile(account_id)
    if me is None:
        await bot.send_message(chat_id, texts.NO_PROFILE)
        return
    mode = await repo.get_search_mode(account_id)
    pool = filter_pool(me, await repo.list_active_profiles(), mode)
    # Цель поиска сужает пул до тех, кто идёт на то же мероприятие (как в мини-приложении).
    event = await repo.get_event(await repo.get_target_event(account_id))
    if event:
        targeting = await repo.ids_targeting(event["id"])
        pool = [p for p in pool if p["user_id"] in targeting]
    feed = build_feed(me, pool, await repo.get_swiped_ids(account_id))
    if not feed:
        if event and not await repo.count_skips(account_id):
            link = await event_link(bot, event["id"])
            await bot.send_message(chat_id, texts.EVENT_FEED_EMPTY.format(title=event["title"], link=link),
                                   reply_markup=kb.event_empty_kb())
            return
        if mode != "all":
            await bot.send_message(chat_id, texts.EMPTY_BY_FILTER.format(label=texts.SEARCH_LABELS[mode]),
                                   reply_markup=kb.settings_hint_kb())
            return
        skipped = await repo.count_skips(account_id)
        if skipped:
            await bot.send_message(chat_id, texts.FEED_EMPTY_AGAIN.format(skipped=skipped), reply_markup=kb.feed_empty_kb())
        else:
            await bot.send_message(chat_id, texts.FEED_EMPTY, reply_markup=kb.main_menu_kb())
        return
    top = feed[0]
    text = card_text(top)
    if event:
        text = texts.EVENT_CARD_LINE.format(title=event["title"]) + "\n\n" + text
    await send(bot, chat_id, text, kb.feed_card_kb(top["profile"]["user_id"]), top["profile"])


async def register_like(account_id: str, target_id: str, message: str = "") -> tuple[bool, dict | None]:
    """Лайк, проверка мэтча, уведомление собеседника в его мессенджер(ы)."""
    me_id = await repo.resolve_id(account_id)
    await repo.save_swipe(me_id, target_id, liked=True, message=message)
    partner = await repo.get_profile(target_id)
    if partner and partner.get("is_test"):
        await repo.save_swipe(target_id, me_id, liked=True)  # тестовые анкеты лайкают в ответ
    likes = await repo.get_likes_involving(me_id)
    matched = bool(partner and is_match(likes, me_id, target_id))
    if partner and not partner.get("is_test"):
        me = await repo.get_profile(me_id) or {}
        if matched:
            note = texts.NEW_MATCH + texts.profile_card(me, show_contact=True)
            if message:
                note += f"\n\n💬 Сообщение: {message}"
            await notify.send_to_profile(
                target_id, note,
                max_attachments=max_media.with_photo(me, max_kb.after_match_kb()),
                tg_markup=kb.as_dict(kb.after_match_kb()),
            )
        else:
            await notify.send_to_profile(
                target_id, "Кто-то оценил твою анкету 👀 Загляни в «Искать сокомандников» — вдруг взаимно!",
                max_attachments=max_kb.liked_nudge_kb(), tg_text=texts.LIKED_NUDGE,
            )
    return matched, partner


async def write_url(partner: dict) -> str | None:
    """Ссылка «Написать» в Telegram — если у человека есть Telegram и в контакте его ник."""
    m = TG_NICK.match((partner.get("username") or "").strip())
    if not m or "tg" not in await repo.profile_platforms(partner["user_id"]):
        return None
    return f"https://t.me/{m.group(1)}"


async def after_swipe(bot: Bot, chat_id: int, account_id: str, matched: bool, partner: dict | None) -> None:
    if matched and partner:
        await send(bot, chat_id, texts.NEW_MATCH + texts.profile_card(partner, show_contact=True),
                   kb.after_match_kb(await write_url(partner)), partner)
    else:
        await show_next(bot, chat_id, account_id)


@router.callback_query(F.data.in_({kb.MENU_FEED, kb.FEED_NEXT}))
async def on_feed(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.clear()
    await drop_buttons(cb)
    await show_next(cb.bot, cb.from_user.id, uid(cb.from_user))


@router.callback_query(F.data == kb.FEED_AGAIN)
async def on_feed_again(cb: CallbackQuery) -> None:
    await cb.answer()
    me = uid(cb.from_user)
    await repo.reset_skips(me)
    await show(cb, texts.FEED_AGAIN_START)
    await show_next(cb.bot, cb.from_user.id, me)


@router.callback_query(F.data.startswith(kb.FEED_LIKE + ":"))
async def on_like(cb: CallbackQuery) -> None:
    await cb.answer("👍")
    await drop_buttons(cb)
    me = uid(cb.from_user)
    matched, partner = await register_like(me, cb.data.split(":", 2)[2])
    await after_swipe(cb.bot, cb.from_user.id, me, matched, partner)


@router.callback_query(F.data.startswith(kb.FEED_SKIP + ":"))
async def on_skip(cb: CallbackQuery) -> None:
    # Без всплывающего уведомления на каждый пропуск — меньше запросов при быстрых свайпах.
    await cb.answer()
    await drop_buttons(cb)
    me = uid(cb.from_user)
    await repo.save_swipe(me, cb.data.split(":", 2)[2], liked=False)
    await show_next(cb.bot, cb.from_user.id, me)


@router.callback_query(F.data.startswith(kb.FEED_MSG + ":"))
async def on_like_with_message(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    await state.set_state(FeedFlow.writing_message)
    await state.update_data(feed_target=cb.data.split(":", 2)[2])
    await cb.bot.send_message(cb.from_user.id, texts.ASK_MESSAGE)


@router.message(FeedFlow.writing_message, F.text)
async def on_feed_message(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not is_clean(text):
        await message.answer(texts.BANNED_WORDS)
        return
    if has_ads(text):
        await message.answer(texts.NO_LINKS_MESSAGE)
        return
    if len(text) > 300:
        await message.answer(texts.TOO_LONG.format(limit=300))
        return
    target = (await state.get_data()).get("feed_target")
    await state.clear()
    me = uid(message.from_user)
    if not target:
        await show_next(message.bot, message.chat.id, me)
        return
    matched, partner = await register_like(me, target, message=text)
    await after_swipe(message.bot, message.chat.id, me, matched, partner)


@router.callback_query(F.data == kb.MENU_MATCHES)
async def on_matches(cb: CallbackQuery) -> None:
    await cb.answer()
    me = await repo.resolve_id(uid(cb.from_user))
    likes = await repo.get_likes_involving(me)
    partner_ids = matches_for(likes, me)
    if not partner_ids:
        await show(cb, texts.NO_MATCHES, kb.back_kb())
        return
    lines = ["🤝 Твои мэтчи:\n"]
    write: list[tuple[str, str]] = []
    for pid in partner_ids:
        p = await repo.get_profile(pid)
        if p:
            lines.append(f"• {p['name']} ({p.get('role') or '—'}) — {p.get('username') or '—'}")
            url = await write_url(p)
            if url:
                write.append((p["name"], url))
    await show(cb, "\n".join(lines), kb.matches_kb(write))


# ---------------------------------------------------------------- настройки поиска

@router.callback_query(F.data == kb.MENU_SETTINGS)
async def on_settings(cb: CallbackQuery) -> None:
    await cb.answer()
    await show(cb, texts.SETTINGS_TEXT, kb.search_settings_kb(await repo.get_search_mode(uid(cb.from_user))))


@router.callback_query(F.data.startswith(kb.SEARCH_MODE + ":"))
async def on_set_mode(cb: CallbackQuery) -> None:
    mode = await repo.set_search_mode(uid(cb.from_user), cb.data.split(":", 2)[2])
    await cb.answer(f"Поиск: {texts.SEARCH_LABELS[mode]}")
    await show(cb, texts.SETTINGS_TEXT, kb.search_settings_kb(mode))


# ---------------------------------------------------------------- одна анкета на оба мессенджера

async def redeem(bot: Bot, user: User, code: str, state: FSMContext, replace: bool = False) -> None:
    try:
        await repo.redeem_link_code(code, uid(user), replace=replace)
    except repo.LinkError as exc:
        if exc.code == "has_profile":
            await state.clear()
            await bot.send_message(user.id, texts.LINK_REPLACE_ASK.format(reason=exc.message),
                                   reply_markup=kb.link_replace_kb(repo.normalize_code(code)))
        else:
            # остаёмся в режиме ввода кода — можно прислать другой
            await state.set_state(LinkFlow.code)
            await bot.send_message(user.id, f"⚠️ {exc.message}", reply_markup=kb.link_cancel_kb())
        return
    await state.clear()
    await bot.send_message(user.id, texts.LINK_DONE)
    await send_menu(bot, user)


@router.callback_query(F.data == kb.LINK_START)
async def on_link_start(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    await state.set_state(LinkFlow.code)
    await cb.bot.send_message(cb.from_user.id, texts.LINK_ASK_CODE, reply_markup=kb.link_cancel_kb())


@router.message(Command("link"))
async def cmd_link(message: Message, command: CommandObject, state: FSMContext) -> None:
    if not command.args:
        await state.set_state(LinkFlow.code)
        await message.answer(texts.LINK_ASK_CODE, reply_markup=kb.link_cancel_kb())
        return
    await redeem(message.bot, message.from_user, command.args, state)


@router.message(LinkFlow.code, F.text)
async def on_link_code(message: Message, state: FSMContext) -> None:
    await redeem(message.bot, message.from_user, message.text, state)


@router.callback_query(F.data.startswith(kb.LINK_REPLACE + ":"))
async def on_link_replace(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await drop_buttons(cb)
    await redeem(cb.bot, cb.from_user, cb.data.split(":", 2)[2], state, replace=True)


@router.callback_query(F.data == kb.LINK_CANCEL)
async def on_link_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.clear()
    await show(cb, texts.LINK_CANCELLED)


@router.callback_query(F.data == kb.MENU_LINK)
async def on_link_code_issue(cb: CallbackQuery) -> None:
    await cb.answer()
    me = uid(cb.from_user)
    profile = await repo.get_profile(me)
    if profile is None:
        await show(cb, texts.NO_PROFILE)
        return
    if "max" in await repo.profile_platforms(profile["user_id"]):
        await show(cb, texts.LINK_ALREADY, kb.back_kb())
        return
    code, _ = await repo.create_link_code(me)
    await drop_buttons(cb)
    await cb.bot.send_message(cb.from_user.id, texts.LINK_CODE.format(code=code), reply_markup=kb.link_code_kb(code))


# ---------------------------------------------------------------- мероприятия

TG_NICK = re.compile(r"^(?:тг:?\s*|tg:?\s*|telegram:?\s*)?@([A-Za-z][A-Za-z0-9_]{4,31})$", re.IGNORECASE)


async def event_link(bot: Bot, event_id: int) -> str:
    """Ссылка, по которой человек сразу попадает в подбор на мероприятие."""
    username = settings.telegram_bot_username
    if not username:
        try:
            username = (await bot.me()).username
        except Exception:
            username = ""
    return f"https://t.me/{username}?start=event-{event_id}" if username else ""


async def events_screen(account_id: str) -> tuple[str, InlineKeyboardMarkup]:
    events = (await repo.list_events())[:10]
    current = await repo.get_target_event(account_id)
    if not events:
        return texts.EVENTS_EMPTY, kb.events_kb([], current)
    body = "\n\n".join(texts.event_card(ev, i, ev["id"] == current) for i, ev in enumerate(events, 1))
    return f"{texts.EVENTS_TITLE}\n\n{body}", kb.events_kb(events, current)


@router.message(Command("events"))
async def cmd_events(message: Message, state: FSMContext) -> None:
    await state.clear()
    text, markup = await events_screen(uid(message.from_user))
    await message.answer(text, reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == kb.MENU_EVENTS)
async def on_events(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.clear()
    text, markup = await events_screen(uid(cb.from_user))
    await drop_buttons(cb)
    await cb.bot.send_message(cb.from_user.id, text, reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith(kb.EVENT_PICK + ":"))
async def on_event_pick(cb: CallbackQuery) -> None:
    me = uid(cb.from_user)
    if not await repo.has_profile(me):
        await cb.answer()
        await show(cb, texts.NO_PROFILE)
        return
    event_id = await repo.set_target_event(me, int(cb.data.split(":", 2)[2]))
    if not event_id:
        await cb.answer()
        await show(cb, texts.EVENT_NOT_FOUND, kb.event_set_kb())
        return
    event = await repo.get_event(event_id)
    await cb.answer("🎯 Цель выбрана")
    await show(cb, texts.EVENT_SET.format(title=event["title"]), kb.event_set_kb())


@router.callback_query(F.data == kb.EVENT_CLEAR)
async def on_event_clear(cb: CallbackQuery) -> None:
    await repo.set_target_event(uid(cb.from_user), None)
    await cb.answer()
    await show(cb, texts.EVENT_CLEARED, kb.event_set_kb())


async def start_with_event(bot: Bot, user: User, raw_id: str, state: FSMContext) -> None:
    event = await repo.get_event(int(raw_id)) if raw_id.isdigit() else None
    if event is None:
        await bot.send_message(user.id, texts.EVENT_NOT_FOUND)
        await greet(bot, user)
        return
    me = uid(user)
    if await repo.has_profile(me):
        await repo.set_target_event(me, event["id"])
        await bot.send_message(user.id, texts.EVENT_SET.format(title=event["title"]), reply_markup=kb.event_set_kb())
        return
    # Анкеты ещё нет: запомним цель и поставим её сразу после сохранения анкеты.
    await state.update_data(pending_event=event["id"])
    await bot.send_message(user.id, texts.EVENT_PENDING.format(title=event["title"]))
    await bot.send_message(user.id, texts.WELCOME, reply_markup=kb.consent_kb())


# ---------------------------------------------------------------- всё остальное

BUTTON_STATES = {Form.degree.state, Form.degree_med.state, Form.course.state, Form.role.state,
                 Form.looking_for.state, Form.confirm.state}


@router.message()
async def on_any_message(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer(texts.UNKNOWN)
    elif current in BUTTON_STATES:
        await message.answer(texts.USE_BUTTONS)
    else:
        await message.answer(texts.EMPTY_TEXT)


@router.callback_query()
async def on_any_callback(cb: CallbackQuery) -> None:
    await cb.answer("Эта кнопка уже неактуальна. Напиши /start", show_alert=False)

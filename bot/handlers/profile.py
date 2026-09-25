# bot/handlers/profile.py
# Анкета: пошаговое заполнение, просмотр, скрытие и удаление (зона Романа).
#
# Шаги: имя → вуз → курс → город → роль → цель → интересы → о себе → GitHub → контакт → подтверждение.
# Пока анкета не подтверждена, ответы лежат в context (FSM), в базу пишем только на шаге «Сохранить».

from maxapi import F
from maxapi.context.base import BaseContext
from maxapi.dispatcher import Router
from maxapi.filters.command import Command
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated
from maxapi.types.attachments.image import Image

from bot import keyboards as kb
from bot import media
from bot import texts
from bot.states import ProfileForm
from core.interests import LOOKING_FOR_OPTIONS, normalize_interests
from core.moderation import has_ads, is_clean, is_valid_contact, normalize_github
from db import repo

router = Router(router_id="profile")

LIMITS = {"name": 50, "university": 100, "city": 60, "about": 500, "github": 200, "username": 100}


def _text(event: MessageCreated) -> str:
    body = event.message.body
    return (body.text or "").strip() if body else ""


async def _take_text(event: MessageCreated, field: str) -> str | None:
    """Достаёт текст из сообщения и проверяет его. None — если нужно спросить ещё раз.

    Проверки: не пусто, не длиннее лимита, без мата/оскорблений/экстремизма (core/moderation),
    без рекламы. Ссылка разрешена только на GitHub и только в поле github; в поле контакта —
    только ник, телефон или e-mail.
    """
    value = _text(event)
    if not value:
        await event.message.answer(texts.EMPTY_TEXT)
        return None
    limit = LIMITS.get(field, 200)
    if len(value) > limit:
        await event.message.answer(texts.TOO_LONG.format(limit=limit))
        return None
    if not is_clean(value):
        await event.message.answer(texts.BANNED_WORDS)
        return None
    if field == "github":
        github = normalize_github(value)
        if github is None:
            await event.message.answer(text=texts.BAD_GITHUB, attachments=kb.skip_kb())
            return None
        return github
    if field == "username":
        if not is_valid_contact(value):
            await event.message.answer(texts.BAD_CONTACT)
            return None
        return value
    if has_ads(value):
        await event.message.answer(texts.NO_LINKS)
        return None
    return value


async def start_form(answer, context: BaseContext, max_username: str | None = None, first_name: str = "") -> None:
    """Начать заполнение анкеты с первого шага. answer — функция отправки сообщения."""
    await context.clear()
    await context.update_data(max_username=max_username or "", first_name=first_name or "")
    await context.set_state(ProfileForm.name)
    await answer(text=texts.ASK_NAME)


# ── Шаги с текстовым ответом ─────────────────────────────────────────────────


@router.message_created(ProfileForm.name, F.message.body.text)
async def step_name(event: MessageCreated, context: BaseContext) -> None:
    value = await _take_text(event, "name")
    if value is None:
        return
    await context.update_data(name=value)
    await context.set_state(ProfileForm.photo)
    await event.message.answer(text=texts.ASK_PHOTO, attachments=kb.skip_kb())


@router.message_created(ProfileForm.photo, F.message.body.attachments)
async def step_photo(event: MessageCreated, context: BaseContext) -> None:
    """Получили фото — сохраняем его токен и идём дальше к вузу."""
    body = event.message.body
    attachments = body.attachments if body else None
    first = attachments[0] if attachments else None
    if isinstance(first, Image) and first.payload and first.payload.token:
        await context.update_data(photo=first.payload.token)
        await _ask_university(event.message.answer, context)
    else:
        await event.message.answer(texts.NO_PHOTO_HINT)


@router.message_created(ProfileForm.photo, F.message.body.text)
async def step_photo_text(event: MessageCreated, context: BaseContext) -> None:
    """На шаге фото прислали текст — подсказываем прислать картинку или пропустить."""
    await event.message.answer(texts.NO_PHOTO_HINT)


@router.message_created(ProfileForm.university, F.message.body.text)
async def step_university(event: MessageCreated, context: BaseContext) -> None:
    value = await _take_text(event, "university")
    if value is None:
        return
    await context.update_data(university=value)
    await context.set_state(ProfileForm.course)
    await event.message.answer(text=texts.ASK_COURSE, attachments=kb.course_kb())


@router.message_created(ProfileForm.city, F.message.body.text)
async def step_city(event: MessageCreated, context: BaseContext) -> None:
    value = await _take_text(event, "city")
    if value is None:
        return
    await context.update_data(city=value)
    await context.set_state(ProfileForm.role)
    await event.message.answer(text=texts.ASK_ROLE, attachments=kb.role_kb())


@router.message_created(ProfileForm.interests, F.message.body.text)
async def step_interests(event: MessageCreated, context: BaseContext) -> None:
    raw = _text(event)
    if not is_clean(raw):
        await event.message.answer(texts.BANNED_WORDS)
        return
    if has_ads(raw):
        await event.message.answer(texts.NO_LINKS)
        return
    interests = normalize_interests(raw)
    if not interests:
        await event.message.answer(texts.NO_INTERESTS)
        return
    await context.update_data(interests=interests)
    await context.set_state(ProfileForm.about)
    await event.message.answer(text=texts.ASK_ABOUT, attachments=kb.skip_kb())


@router.message_created(ProfileForm.about, F.message.body.text)
async def step_about(event: MessageCreated, context: BaseContext) -> None:
    value = await _take_text(event, "about")
    if value is None:
        return
    await context.update_data(about=value)
    await _ask_github(event.message.answer, context)


@router.message_created(ProfileForm.github, F.message.body.text)
async def step_github(event: MessageCreated, context: BaseContext) -> None:
    value = await _take_text(event, "github")
    if value is None:
        return
    await context.update_data(github=value)
    await _ask_contact(event.message.answer, context)


@router.message_created(ProfileForm.contact, F.message.body.text)
async def step_contact(event: MessageCreated, context: BaseContext) -> None:
    value = await _take_text(event, "username")
    if value is None:
        return
    await context.update_data(username=value)
    await _show_confirm(event.message.answer, context)


# ── Шаги с кнопками ──────────────────────────────────────────────────────────


@router.message_callback(ProfileForm.course, F.callback.payload.startswith("course:"))
async def step_course(event: MessageCallback, context: BaseContext) -> None:
    course = int(event.callback.payload.split(":", 1)[1])
    await event.answer()
    await context.update_data(course=course)
    await context.set_state(ProfileForm.city)
    await event.message.answer(texts.ASK_CITY)


@router.message_callback(ProfileForm.role, F.callback.payload.startswith("role:"))
async def step_role(event: MessageCallback, context: BaseContext) -> None:
    index = int(event.callback.payload.split(":", 1)[1])
    await event.answer(notification=f"Роль: {kb.ROLES[index]}")
    await context.update_data(role=kb.ROLES[index])
    await context.set_state(ProfileForm.looking_for)
    await event.message.answer(text=texts.ASK_LOOKING_FOR, attachments=kb.looking_for_kb())


@router.message_callback(ProfileForm.looking_for, F.callback.payload.startswith("goal:"))
async def step_looking_for(event: MessageCallback, context: BaseContext) -> None:
    index = int(event.callback.payload.split(":", 1)[1])
    await event.answer(notification=f"Ищешь: {LOOKING_FOR_OPTIONS[index]}")
    await context.update_data(looking_for=LOOKING_FOR_OPTIONS[index])
    await context.set_state(ProfileForm.interests)
    await event.message.answer(texts.ASK_INTERESTS)


@router.message_callback(F.callback.payload == kb.SKIP)
async def step_skip(event: MessageCallback, context: BaseContext) -> None:
    """«Пропустить» на необязательных шагах: курс, о себе, GitHub."""
    await event.answer()
    state = str(await context.get_state())
    if state == str(ProfileForm.photo):
        await context.update_data(photo="")
        await _ask_university(event.message.answer, context)
    elif state == str(ProfileForm.course):
        await context.update_data(course=None)
        await context.set_state(ProfileForm.city)
        await event.message.answer(texts.ASK_CITY)
    elif state == str(ProfileForm.about):
        await context.update_data(about="")
        await _ask_github(event.message.answer, context)
    elif state == str(ProfileForm.github):
        await context.update_data(github="")
        await _ask_contact(event.message.answer, context)


@router.message_callback(ProfileForm.contact, F.callback.payload == kb.USE_MY_USERNAME)
async def step_contact_username(event: MessageCallback, context: BaseContext) -> None:
    await event.answer()
    data = await context.get_data()
    await context.update_data(username="@" + data.get("max_username", ""))
    await _show_confirm(event.message.answer, context)


@router.message_callback(ProfileForm.confirm, F.callback.payload == kb.CONFIRM_SAVE)
async def step_save(event: MessageCallback, context: BaseContext) -> None:
    data = await context.get_data()
    await repo.save_profile(event.callback.user.user_id, data)
    await context.clear()
    await event.edit(text=texts.PROFILE_SAVED, attachments=[])
    await event.message.answer(text=texts.MAIN_MENU, attachments=kb.main_menu_kb())


@router.message_callback(ProfileForm.confirm, F.callback.payload == kb.CONFIRM_RESTART)
async def step_restart(event: MessageCallback, context: BaseContext) -> None:
    await event.answer()
    data = await context.get_data()
    await start_form(event.message.answer, context, data.get("max_username"), data.get("first_name", ""))


# ── Переходы между шагами ────────────────────────────────────────────────────


async def _ask_university(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.university)
    await answer(text=texts.ASK_UNIVERSITY)


async def _ask_github(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.github)
    await answer(text=texts.ASK_GITHUB, attachments=kb.skip_kb())


async def _ask_contact(answer, context: BaseContext) -> None:
    data = await context.get_data()
    await context.set_state(ProfileForm.contact)
    await answer(text=texts.ASK_CONTACT, attachments=kb.contact_kb(data.get("max_username")))


async def _show_confirm(answer, context: BaseContext) -> None:
    data = await context.get_data()
    await context.set_state(ProfileForm.confirm)
    card = texts.profile_card(data, show_contact=True)
    await answer(text=f"Проверь анкету:\n\n{card}", attachments=media.with_photo(data, kb.confirm_kb()))


# ── Просмотр и управление анкетой ────────────────────────────────────────────


async def _profile_screen(user_id: int) -> tuple[str, list]:
    profile = await repo.get_profile(user_id)
    if profile is None:
        return texts.NO_PROFILE, []
    card = texts.profile_card(profile, show_contact=True)
    if not profile.get("is_active", True):
        card += "\n\n🙈 Анкета скрыта из поиска."
    return card, kb.profile_kb(is_active=profile.get("is_active", True))


@router.message_created(Command("profile"))
async def cmd_profile(event: MessageCreated) -> None:
    text, attachments = await _profile_screen(event.message.sender.user_id)
    await event.message.answer(text=text, attachments=attachments)


@router.message_callback(F.callback.payload == kb.MENU_PROFILE)
async def on_profile(event: MessageCallback) -> None:
    text, attachments = await _profile_screen(event.callback.user.user_id)
    await event.edit(text=text, attachments=attachments)


@router.message_callback(F.callback.payload == kb.MENU_EDIT)
async def on_edit(event: MessageCallback, context: BaseContext) -> None:
    await event.answer()
    user = event.callback.user
    await start_form(event.message.answer, context, max_username=user.username, first_name=user.first_name)


@router.message_callback(F.callback.payload == kb.MENU_HIDE)
async def on_hide(event: MessageCallback) -> None:
    await repo.set_active(event.callback.user.user_id, False)
    await event.edit(text=texts.PROFILE_HIDDEN, attachments=kb.profile_kb(is_active=False))


@router.message_callback(F.callback.payload == kb.MENU_SHOW)
async def on_show(event: MessageCallback) -> None:
    await repo.set_active(event.callback.user.user_id, True)
    await event.edit(text=texts.PROFILE_SHOWN, attachments=kb.profile_kb(is_active=True))


@router.message_callback(F.callback.payload == kb.MENU_DELETE)
async def on_delete(event: MessageCallback) -> None:
    await event.edit(text=texts.DELETE_ASK, attachments=kb.delete_confirm_kb())


@router.message_callback(F.callback.payload == kb.MENU_DELETE_CONFIRM)
async def on_delete_confirm(event: MessageCallback, context: BaseContext) -> None:
    await repo.delete_profile(event.callback.user.user_id)
    await context.clear()
    await event.edit(text=texts.DELETED, attachments=[])

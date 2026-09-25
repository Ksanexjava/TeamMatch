# bot/handlers/profile.py
# Анкета: пошаговое заполнение, просмотр, скрытие и удаление (зона Романа).
#
# Шаги: имя → фото → вуз → уровень образования → курс → направление → город → роль → цель → интересы → о себе → GitHub → контакт → подтверждение.
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

LIMITS = {
    "name": 50, "university": 100, "course": 2, "direction": 100, "city": 60,
    "about": 500, "github": 200, "username": 100,
}


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
    await _advance(event.message.answer, context, "name", lambda: _ask_photo(event.message.answer, context))


@router.message_created(ProfileForm.photo, F.message.body.attachments)
async def step_photo(event: MessageCreated, context: BaseContext) -> None:
    """Получили фото — сохраняем его токен и идём дальше к вузу."""
    body = event.message.body
    attachments = body.attachments if body else None
    first = attachments[0] if attachments else None
    if isinstance(first, Image) and first.payload and first.payload.token:
        await context.update_data(photo=first.payload.token)
        await _advance(event.message.answer, context, "photo", lambda: _ask_university(event.message.answer, context))
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
    await _advance(event.message.answer, context, "university", lambda: _ask_degree(event.message.answer, context))


@router.message_created(ProfileForm.course_manual, F.message.body.text)
async def step_course_manual(event: MessageCreated, context: BaseContext) -> None:
    """Медики вводят курс сами (специалитет — до 6 лет, ординатура — свой счёт)."""
    value = await _take_text(event, "course")
    if value is None:
        return
    if not value.isdigit() or not 1 <= int(value) <= 10:
        await event.message.answer(texts.BAD_COURSE)
        return
    await context.update_data(course=int(value))
    await _advance(event.message.answer, context, "course", lambda: _ask_direction(event.message.answer, context))


@router.message_created(ProfileForm.direction, F.message.body.text)
async def step_direction(event: MessageCreated, context: BaseContext) -> None:
    value = await _take_text(event, "direction")
    if value is None:
        return
    await context.update_data(direction=value)
    await _advance(event.message.answer, context, "direction", lambda: _ask_city(event.message.answer, context))


@router.message_created(ProfileForm.city, F.message.body.text)
async def step_city(event: MessageCreated, context: BaseContext) -> None:
    value = await _take_text(event, "city")
    if value is None:
        return
    await context.update_data(city=value)
    await _advance(event.message.answer, context, "city", lambda: _ask_role(event.message.answer, context))


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
    await _advance(event.message.answer, context, "interests", lambda: _ask_about(event.message.answer, context))


@router.message_created(ProfileForm.about, F.message.body.text)
async def step_about(event: MessageCreated, context: BaseContext) -> None:
    value = await _take_text(event, "about")
    if value is None:
        return
    await context.update_data(about=value)
    await _advance(event.message.answer, context, "about", lambda: _ask_github(event.message.answer, context))


@router.message_created(ProfileForm.github, F.message.body.text)
async def step_github(event: MessageCreated, context: BaseContext) -> None:
    value = await _take_text(event, "github")
    if value is None:
        return
    await context.update_data(github=value)
    await _advance(event.message.answer, context, "github", lambda: _ask_contact(event.message.answer, context))


@router.message_created(ProfileForm.contact, F.message.body.text)
async def step_contact(event: MessageCreated, context: BaseContext) -> None:
    value = await _take_text(event, "username")
    if value is None:
        return
    await context.update_data(username=value)
    await _advance(event.message.answer, context, "username", lambda: _show_confirm(event.message.answer, context))


# ── Шаги с кнопками ──────────────────────────────────────────────────────────


@router.message_callback(ProfileForm.degree, F.callback.payload == kb.DEGREE_OTHER)
async def step_degree_other(event: MessageCallback, context: BaseContext) -> None:
    """«Другое» — считаем, что это медик: спрашиваем специалитет или ординатуру."""
    await event.answer()
    await context.set_state(ProfileForm.degree_med)
    await event.message.answer(text=texts.ASK_DEGREE_MED, attachments=kb.degree_med_kb())


@router.message_callback(ProfileForm.degree, F.callback.payload.startswith("degree:"))
async def step_degree(event: MessageCallback, context: BaseContext) -> None:
    label, value, max_courses = kb.DEGREES[int(event.callback.payload.split(":", 1)[1])]
    await event.answer(notification=label)
    await context.update_data(degree=value)
    await context.set_state(ProfileForm.course)
    await event.message.answer(text=texts.ASK_COURSE, attachments=kb.course_kb(max_courses))


@router.message_callback(ProfileForm.degree_med, F.callback.payload.startswith("degmed:"))
async def step_degree_med(event: MessageCallback, context: BaseContext) -> None:
    label, value, _ = kb.MED_DEGREES[int(event.callback.payload.split(":", 1)[1])]
    await event.answer(notification=label)
    await context.update_data(degree=value)
    await context.set_state(ProfileForm.course_manual)
    await event.message.answer(texts.ASK_COURSE_MANUAL)


@router.message_callback(ProfileForm.course, F.callback.payload.startswith("course:"))
async def step_course(event: MessageCallback, context: BaseContext) -> None:
    course = int(event.callback.payload.split(":", 1)[1])
    await event.answer()
    await context.update_data(course=course)
    await _advance(event.message.answer, context, "course", lambda: _ask_direction(event.message.answer, context))


@router.message_callback(ProfileForm.role, F.callback.payload.startswith("role:"))
async def step_role(event: MessageCallback, context: BaseContext) -> None:
    index = int(event.callback.payload.split(":", 1)[1])
    await event.answer(notification=f"Роль: {kb.ROLES[index]}")
    await context.update_data(role=kb.ROLES[index])
    await _advance(event.message.answer, context, "role", lambda: _ask_looking_for(event.message.answer, context))


@router.message_callback(ProfileForm.looking_for, F.callback.payload.startswith("goal:"))
async def step_looking_for(event: MessageCallback, context: BaseContext) -> None:
    index = int(event.callback.payload.split(":", 1)[1])
    await event.answer(notification=f"Ищешь: {LOOKING_FOR_OPTIONS[index]}")
    await context.update_data(looking_for=LOOKING_FOR_OPTIONS[index])
    await _advance(event.message.answer, context, "looking_for", lambda: _ask_interests(event.message.answer, context))


@router.message_callback(F.callback.payload == kb.SKIP)
async def step_skip(event: MessageCallback, context: BaseContext) -> None:
    """«Пропустить» на необязательных шагах: фото, о себе, GitHub."""
    await event.answer()
    state = str(await context.get_state())
    answer = event.message.answer
    if state == str(ProfileForm.photo):
        await context.update_data(photo="")
        await _advance(answer, context, "photo", lambda: _ask_university(answer, context))
    elif state == str(ProfileForm.about):
        await context.update_data(about="")
        await _advance(answer, context, "about", lambda: _ask_github(answer, context))
    elif state == str(ProfileForm.github):
        await context.update_data(github="")
        await _advance(answer, context, "github", lambda: _ask_contact(answer, context))


@router.message_callback(ProfileForm.contact, F.callback.payload == kb.USE_MY_USERNAME)
async def step_contact_username(event: MessageCallback, context: BaseContext) -> None:
    await event.answer()
    data = await context.get_data()
    await context.update_data(username="@" + data.get("max_username", ""))
    await _advance(event.message.answer, context, "username", lambda: _show_confirm(event.message.answer, context))


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


async def _advance(answer, context: BaseContext, done_field: str, next_step) -> None:
    """Перейти к следующему шагу — или, если это точечное редактирование, сохранить и выйти.

    В режиме редактирования в context лежат edit_user_id и edit_last — поле, на котором
    редактирование заканчивается (для «Образования» это direction: уровень → курс → направление).
    """
    data = await context.get_data()
    if data.get("edit_last") != done_field:
        await next_step()
        return
    user_id = data["edit_user_id"]
    await repo.save_profile(user_id, data)
    await context.clear()
    text, attachments = await _profile_screen(user_id)
    profile = await repo.get_profile(user_id)
    await answer(text=f"{texts.EDIT_SAVED}\n\n{text}", attachments=media.with_photo(profile, attachments))


async def _ask_photo(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.photo)
    await answer(text=texts.ASK_PHOTO, attachments=kb.skip_kb())


async def _ask_degree(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.degree)
    await answer(text=texts.ASK_DEGREE, attachments=kb.degree_kb())


async def _ask_city(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.city)
    await answer(texts.ASK_CITY)


async def _ask_role(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.role)
    await answer(text=texts.ASK_ROLE, attachments=kb.role_kb())


async def _ask_looking_for(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.looking_for)
    await answer(text=texts.ASK_LOOKING_FOR, attachments=kb.looking_for_kb())


async def _ask_interests(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.interests)
    await answer(texts.ASK_INTERESTS)


async def _ask_about(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.about)
    await answer(text=texts.ASK_ABOUT, attachments=kb.skip_kb())


async def _ask_name(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.name)
    await answer(text=texts.ASK_NAME)


async def _ask_university(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.university)
    await answer(text=texts.ASK_UNIVERSITY)


async def _ask_direction(answer, context: BaseContext) -> None:
    await context.set_state(ProfileForm.direction)
    await answer(text=texts.ASK_DIRECTION)


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


# ── Точечное редактирование ──────────────────────────────────────────────────

# Что редактируем: первый шаг и поле, после которого сохраняем.
# «Образование» проходит уровень → курс → направление и сохраняется после направления.
EDIT_STEPS = {
    "name": (_ask_name, "name"),
    "photo": (_ask_photo, "photo"),
    "university": (_ask_university, "university"),
    "education": (_ask_degree, "direction"),
    "direction": (_ask_direction, "direction"),
    "city": (_ask_city, "city"),
    "role": (_ask_role, "role"),
    "looking_for": (_ask_looking_for, "looking_for"),
    "interests": (_ask_interests, "interests"),
    "about": (_ask_about, "about"),
    "github": (_ask_github, "github"),
    "contact": (_ask_contact, "username"),
}


@router.message_callback(F.callback.payload == kb.MENU_EDIT_FIELDS)
async def on_edit_fields(event: MessageCallback, context: BaseContext) -> None:
    """«Редактировать анкету» — список полей, которые можно поменять по одному."""
    await context.clear()
    await event.edit(text=texts.EDIT_CHOOSE, attachments=kb.edit_fields_kb())


@router.message_callback(F.callback.payload.startswith(kb.EDIT_FIELD + ":"))
async def on_edit_field(event: MessageCallback, context: BaseContext) -> None:
    """Выбрали поле: подгружаем текущую анкету в context и задаём один вопрос."""
    key = event.callback.payload.split(":", 1)[1]
    if key not in EDIT_STEPS:
        await event.answer()
        return
    user = event.callback.user
    profile = await repo.get_profile(user.user_id)
    if profile is None:
        await event.edit(text=texts.NO_PROFILE, attachments=[])
        return
    await event.answer()
    ask, last = EDIT_STEPS[key]
    await context.clear()
    await context.update_data(
        **profile, max_username=user.username or "", edit_user_id=user.user_id, edit_last=last
    )
    try:
        await event.edit(text=texts.EDIT_CHOOSE, attachments=[])   # убираем кнопки со списка
    except Exception:
        pass
    await ask(event.message.answer, context)


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

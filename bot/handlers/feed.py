from maxapi import F
from maxapi.context.base import BaseContext
from maxapi.dispatcher import Router
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

from bot import keyboards as kb
from bot import media
from bot import texts
from bot.states import FeedFlow
from core.interactions import is_match, matches_for
from core.moderation import has_ads, is_clean
from core.recommendations import build_feed, explain
from db import repo

router = Router(router_id="feed")

FEED_EMPTY = "На сегодня подходящие анкеты закончились 👀 Загляни позже — появятся новые."
FEED_EMPTY_AGAIN = (
    "Новые анкеты закончились 👀\n\n"
    "Ты пропустил(а) анкет: {skipped}. Можно пройтись по ним ещё раз — вдруг кто-то теперь "
    "подойдёт. Лайкнутых повторно не покажу: если они ответят взаимностью, придёт мэтч."
)
FEED_AGAIN_START = "🔄 Показываю пропущенные анкеты заново."
ASK_MESSAGE = "Напиши короткое сообщение — человек увидит его, если лайкнет в ответ:"
NO_MATCHES = "Пока мэтчей нет. Полайкай анкеты в «Искать сокомандников» 🙂"
LIKED_NUDGE = "Кто-то оценил твою анкету 👀 Загляни в «Искать сокомандников» — вдруг взаимно!"

SETTINGS_TEXT = (
    "⚙️ Настройки поиска\n\n"
    "Кого показывать в ленте:\n"
    "• Все подходящие — по совместимости, без ограничений\n"
    "• Только мой вуз — люди из твоего вуза\n"
    "• Только мой город — люди из твоего города\n\n"
    "Текущий вариант отмечен ✅."
)
EMPTY_BY_FILTER = (
    "По фильтру «{label}» подходящих анкет пока нет 👀\n"
    "Можно сменить настройки поиска — показать всех или выбрать другой фильтр."
)
SEARCH_LABELS = {"all": "все подходящие", "university": "только мой вуз", "city": "только мой город"}

def _card(item: dict) -> str:
    """Карточка кандидата + строка «почему подходит»."""
    return f"{texts.profile_card(item['profile'])}\n\n⚡ {explain(item['details'])}"


def _match_text(partner: dict) -> str:
    """Сообщение о мэтче с карточкой собеседника и его контактом."""
    return "🎉 У тебя новый мэтч!\n\n" + texts.profile_card(partner, show_contact=True)


async def _send_to(event, user_id: str, text: str, attachments=None) -> None:
    """Отправить сообщение другому пользователю. Тестовым анкетам (id вида u001) не пишем."""
    try:
        if str(user_id).isdigit():
            await event.bot.send_message(user_id=int(user_id), text=text, attachments=attachments or [])
    except Exception:
        pass 


async def _keep_info(event, profile) -> None:
    """Убрать кнопки (и фото) со старой карточки, оставив только текст-инфо."""
    if not profile:
        return
    try:
        await event.edit(text=texts.profile_card(profile), attachments=[])
    except Exception:
        pass

_search_mode: dict[str, str] = {}


def _get_mode(user_id) -> str:
    return _search_mode.get(str(user_id), "all")


def _set_mode(user_id, mode: str) -> None:
    _search_mode[str(user_id)] = mode


def _filter_pool(me: dict, pool: list, mode: str) -> list:
    """Оставить в ленте только анкеты того же вуза/города (для 'all' — не фильтруем)."""
    if mode == "university":
        key = (me.get("university") or "").strip().lower()
        return [p for p in pool if key and (p.get("university") or "").strip().lower() == key]
    if mode == "city":
        key = (me.get("city") or "").strip().lower()
        return [p for p in pool if key and (p.get("city") or "").strip().lower() == key]
    return pool


async def _show_next(me_id, send) -> None:
    """Прислать НОВЫМ сообщением следующую анкету из ленты (с фото, если есть)."""
    me = await repo.get_profile(me_id)
    if me is None:
        await send(text=texts.NO_PROFILE)
        return
    mode = _get_mode(me_id)
    pool = _filter_pool(me, await repo.list_active_profiles(), mode)
    swiped = await repo.get_swiped_ids(me_id)
    feed = build_feed(me, pool, swiped)
    if not feed:
        if mode != "all":
            await send(text=EMPTY_BY_FILTER.format(label=SEARCH_LABELS[mode]), attachments=kb.settings_hint_kb())
            return
        skipped = await repo.count_skips(me_id)
        if skipped:
            await send(text=FEED_EMPTY_AGAIN.format(skipped=skipped), attachments=kb.feed_empty_kb())
        else:
            await send(text=FEED_EMPTY, attachments=kb.main_menu_kb())
        return
    profile = feed[0]["profile"]
    await send(text=_card(feed[0]), attachments=media.with_photo(profile, kb.feed_card_kb(profile["user_id"])))


async def _register_like(event, me_id, target_id: str, message: str = "") -> tuple[bool, dict | None]:
    """Записать лайк, поймать мэтч, уведомить собеседника. Возвращает (мэтч?, анкета собеседника)."""
    await repo.save_swipe(me_id, target_id, liked=True, message=message)
    partner = await repo.get_profile(target_id)

    if partner and partner.get("is_test"):
        await repo.save_swipe(target_id, me_id, liked=True)

    likes = await repo.get_likes_involving(me_id)
    matched = bool(partner and is_match(likes, str(me_id), str(target_id)))

    if matched:
        me = await repo.get_profile(me_id) or {}
        note = _match_text(me)
        if message:
            note += f"\n\n💬 Сообщение: {message}"
        await _send_to(event, target_id, note, media.with_photo(me, kb.after_match_kb()))
    elif partner and not partner.get("is_test"):
     
        await _send_to(event, target_id, LIKED_NUDGE, kb.liked_nudge_kb())

    return matched, partner


async def _after_swipe(event, me_id, matched: bool, partner: dict | None) -> None:
    """Что показать мне после лайка: сообщение о мэтче с кнопками — или следующую анкету."""
    if matched and partner:
        await event.message.answer(
            text=_match_text(partner),
            attachments=media.with_photo(partner, kb.after_match_kb()),
        )
    else:
        await _show_next(me_id, event.message.answer)

#Лента
@router.message_callback(F.callback.payload == kb.MENU_FEED)
async def on_feed(event: MessageCallback) -> None:
    await event.answer()
    await _show_next(event.callback.user.user_id, event.message.answer)


@router.message_callback(F.callback.payload == kb.FEED_AGAIN)
async def on_feed_again(event: MessageCallback) -> None:
    """«Посмотреть пропущенные снова»: забываем пропуски и начинаем ленту заново."""
    await event.answer()
    me_id = event.callback.user.user_id
    await repo.reset_skips(me_id)
    try:
        await event.edit(text=FEED_AGAIN_START, attachments=[]) 
    except Exception:
        pass
    await _show_next(me_id, event.message.answer)
    
# Настройки поиска

@router.message_callback(F.callback.payload == kb.MENU_SETTINGS)
async def on_settings(event: MessageCallback) -> None:
    """Экран настроек поиска: показать текущий режим ленты."""
    await event.answer()
    mode = _get_mode(event.callback.user.user_id)
    await event.edit(text=SETTINGS_TEXT, attachments=kb.search_settings_kb(mode))


@router.message_callback(F.callback.payload.startswith(kb.SEARCH_MODE + ":"))
async def on_set_search_mode(event: MessageCallback) -> None:
    """Пользователь выбрал режим поиска — запоминаем и обновляем экран настроек."""
    mode = event.callback.payload.split(":", 2)[2]
    if mode not in SEARCH_LABELS:
        mode = "all"
    _set_mode(event.callback.user.user_id, mode)
    await event.answer(notification=f"Поиск: {SEARCH_LABELS[mode]}")
    await event.edit(text=SETTINGS_TEXT, attachments=kb.search_settings_kb(mode))


@router.message_callback(F.callback.payload == kb.NUDGE_DISMISS)
async def on_nudge_dismiss(event: MessageCallback) -> None:
    """«Не сейчас» на уведомлении «тебя оценили» — просто убираем кнопки."""
    await event.answer()
    try:
        await event.edit(text=LIKED_NUDGE, attachments=[])
    except Exception:
        pass


@router.message_callback(F.callback.payload.startswith(kb.FEED_LIKE + ":"))
async def on_like(event: MessageCallback) -> None:
    await event.answer(notification="👍")
    me_id = event.callback.user.user_id
    target_id = event.callback.payload.split(":", 2)[2]
    matched, partner = await _register_like(event, me_id, target_id)
    await _keep_info(event, partner)  
    await _after_swipe(event, me_id, matched, partner)


@router.message_callback(F.callback.payload.startswith(kb.FEED_SKIP + ":"))
async def on_skip(event: MessageCallback) -> None:
    await event.answer(notification="👎")
    me_id = event.callback.user.user_id
    target_id = event.callback.payload.split(":", 2)[2]
    await repo.save_swipe(me_id, target_id, liked=False)
    await _keep_info(event, await repo.get_profile(target_id)) 
    await _show_next(me_id, event.message.answer)


@router.message_callback(F.callback.payload.startswith(kb.FEED_MSG + ":"))
async def on_like_with_message(event: MessageCallback, context: BaseContext) -> None:
    await event.answer()
    target_id = event.callback.payload.split(":", 2)[2]
    await context.update_data(feed_target=target_id)
    await context.set_state(FeedFlow.writing_message)
    await _keep_info(event, await repo.get_profile(target_id)) 
    await event.message.answer(text=ASK_MESSAGE)


@router.message_created(FeedFlow.writing_message, F.message.body.text)
async def on_feed_message(event: MessageCreated, context: BaseContext) -> None:
    body = event.message.body
    message = (body.text or "").strip() if body else ""
   
    if not is_clean(message):
        await event.message.answer(texts.BANNED_WORDS)
        return
    if has_ads(message):
        await event.message.answer(texts.NO_LINKS_MESSAGE)
        return
    data = await context.get_data()
    target_id = data.get("feed_target")
    me_id = event.message.sender.user_id
    await context.clear()
    if not target_id:
        await _show_next(me_id, event.message.answer)
        return
    matched, partner = await _register_like(event, me_id, target_id, message=message)
    await _after_swipe(event, me_id, matched, partner)


#Мои мэтчи


@router.message_callback(F.callback.payload == kb.MENU_MATCHES)
async def on_matches(event: MessageCallback) -> None:
    await event.answer()
    me_id = event.callback.user.user_id
    likes = await repo.get_likes_involving(me_id)
    partner_ids = matches_for(likes, str(me_id))
    if not partner_ids:
        await event.edit(text=NO_MATCHES, attachments=kb.back_kb())
        return
    lines = ["🤝 Твои мэтчи:\n"]
    for pid in partner_ids:
        p = await repo.get_profile(pid)
        if p:
            lines.append(f"• {p['name']} ({p.get('role', '—')}) — {p.get('username') or '—'}")
    await event.edit(text="\n".join(lines), attachments=kb.back_kb())

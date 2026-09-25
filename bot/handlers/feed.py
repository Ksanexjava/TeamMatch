# bot/handlers/feed.py
# Лента анкет, лайк / лайк+сообщение / пропуск, мэтчи, уведомления.
#
# Логика подбора — в core/ (recommendations, interactions), данные — через db/repo.
# Карточки отправляются НОВЫМИ сообщениями и ОСТАЮТСЯ в чате как история свайпов, но у
# старой карточки при свайпе убираются кнопки (остаётся только инфо) — активные кнопки
# живут только на текущей карточке внизу. Reply-клавиатуры в MAX нет, только inline.

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
        pass  # человек мог не открывать бота — молча пропускаем, не роняем бота


async def _keep_info(event, profile) -> None:
    """Убрать кнопки (и фото) со старой карточки, оставив только текст-инфо."""
    if not profile:
        return
    try:
        await event.edit(text=texts.profile_card(profile), attachments=[])
    except Exception:
        pass


async def _show_next(me_id, send) -> None:
    """Прислать НОВЫМ сообщением следующую анкету из ленты (с фото, если есть)."""
    me = await repo.get_profile(me_id)
    if me is None:
        await send(text=texts.NO_PROFILE)
        return
    pool = await repo.list_active_profiles()
    swiped = await repo.get_swiped_ids(me_id)
    feed = build_feed(me, pool, swiped)
    if not feed:
        # Анкеты кончились. Если что-то пропускали — предлагаем пройтись по кругу ещё раз.
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

    # Тестовые анкеты лайкают в ответ автоматически — чтобы проверяющий (жюри)
    # мог получить мэтч в одиночку: живых людей в боте на проверке ещё нет.
    if partner and partner.get("is_test"):
        await repo.save_swipe(target_id, me_id, liked=True)

    likes = await repo.get_likes_involving(me_id)
    matched = bool(partner and is_match(likes, str(me_id), str(target_id)))

    if matched:
        # Собеседнику бот пишет сам (даже если он не в чате) — карточка с моим фото и контактом.
        me = await repo.get_profile(me_id) or {}
        note = _match_text(me)
        if message:
            note += f"\n\n💬 Сообщение: {message}"
        await _send_to(event, target_id, note, media.with_photo(me, []))
    elif partner and not partner.get("is_test"):
        # Ещё не мэтч, но человек реальный — мягко подсказываем заглянуть в ленту.
        await _send_to(event, target_id, LIKED_NUDGE)

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


# ── Лента ─────────────────────────────────────────────────────────────────────


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
        await event.edit(text=FEED_AGAIN_START, attachments=[])   # убираем кнопки со старого сообщения
    except Exception:
        pass
    await _show_next(me_id, event.message.answer)


@router.message_callback(F.callback.payload.startswith(kb.FEED_LIKE + ":"))
async def on_like(event: MessageCallback) -> None:
    await event.answer(notification="👍")
    me_id = event.callback.user.user_id
    target_id = event.callback.payload.split(":", 2)[2]
    matched, partner = await _register_like(event, me_id, target_id)
    await _keep_info(event, partner)  # старая карточка — без кнопок, только инфо
    await _after_swipe(event, me_id, matched, partner)


@router.message_callback(F.callback.payload.startswith(kb.FEED_SKIP + ":"))
async def on_skip(event: MessageCallback) -> None:
    await event.answer(notification="👎")
    me_id = event.callback.user.user_id
    target_id = event.callback.payload.split(":", 2)[2]
    await repo.save_swipe(me_id, target_id, liked=False)
    await _keep_info(event, await repo.get_profile(target_id))  # старая карточка — без кнопок
    await _show_next(me_id, event.message.answer)


@router.message_callback(F.callback.payload.startswith(kb.FEED_MSG + ":"))
async def on_like_with_message(event: MessageCallback, context: BaseContext) -> None:
    await event.answer()
    target_id = event.callback.payload.split(":", 2)[2]
    await context.update_data(feed_target=target_id)
    await context.set_state(FeedFlow.writing_message)
    await _keep_info(event, await repo.get_profile(target_id))  # убираем кнопки со старой карточки
    await event.message.answer(text=ASK_MESSAGE)


@router.message_created(FeedFlow.writing_message, F.message.body.text)
async def on_feed_message(event: MessageCreated, context: BaseContext) -> None:
    body = event.message.body
    message = (body.text or "").strip() if body else ""
    # Сообщение уйдёт другому человеку — мат и рекламу не пропускаем, ждём новый текст
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


# ── Мои мэтчи ─────────────────────────────────────────────────────────────────


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

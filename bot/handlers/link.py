"""Одна анкета на человека: подключение Telegram к анкете из MAX и наоборот.

Как это работает:
  • в мессенджере, где анкета уже есть, человек получает одноразовый код (10 минут);
  • во втором мессенджере вводит код — и его аккаунт привязывается к той же анкете.
Код видит только владелец анкеты, поэтому чужую анкету так не присвоить.
"""

from maxapi import F
from maxapi.context.base import BaseContext
from maxapi.dispatcher import Router
from maxapi.filters.command import Command
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

from bot import keyboards as kb
from bot import texts
from bot.states import LinkFlow
from db import repo

router = Router(router_id="link")


async def redeem(answer, user_id: int, code: str, context: BaseContext, replace: bool = False) -> None:
    """Попробовать привязать аккаунт MAX по коду и ответить пользователю."""
    try:
        await repo.redeem_link_code(code, str(user_id), replace=replace)
    except repo.LinkError as exc:
        if exc.code == "has_profile":
            await answer(
                text=exc.message + ".\n\nУдалить анкету в MAX и подключиться к анкете из Telegram? "
                "Лайки и мэтчи этой анкеты тоже удалятся.",
                attachments=kb.link_replace_kb(repo.normalize_code(code)),
            )
        else:
            await answer(text=f"⚠️ {exc.message}", attachments=kb.link_cancel_kb())
            return  # остаёмся в состоянии ввода кода — можно прислать другой
        await context.clear()
        return
    await context.clear()
    await answer(text=texts.LINK_DONE, attachments=[])
    await answer(text=texts.MAIN_MENU, attachments=kb.main_menu_kb())


@router.message_callback(F.callback.payload == kb.LINK_START)
async def on_link_start(event: MessageCallback, context: BaseContext) -> None:
    await event.answer()
    await context.set_state(LinkFlow.code)
    await event.message.answer(text=texts.LINK_ASK_CODE, attachments=kb.link_cancel_kb())


@router.message_created(Command("link"))
async def cmd_link(event: MessageCreated, context: BaseContext) -> None:
    """/link <код> — то же самое одной командой."""
    body = event.message.body
    parts = ((body.text if body else "") or "").split(maxsplit=1)
    if len(parts) < 2:
        await context.set_state(LinkFlow.code)
        await event.message.answer(text=texts.LINK_ASK_CODE, attachments=kb.link_cancel_kb())
        return
    await redeem(event.message.answer, event.message.sender.user_id, parts[1], context)


@router.message_created(LinkFlow.code, F.message.body.text)
async def on_code(event: MessageCreated, context: BaseContext) -> None:
    await redeem(event.message.answer, event.message.sender.user_id, event.message.body.text, context)


@router.message_callback(F.callback.payload.startswith(kb.LINK_REPLACE + ":"))
async def on_replace(event: MessageCallback, context: BaseContext) -> None:
    await event.answer()
    code = event.callback.payload.split(":", 2)[2]
    await redeem(event.message.answer, event.callback.user.user_id, code, context, replace=True)


@router.message_callback(F.callback.payload == kb.LINK_CANCEL)
async def on_cancel(event: MessageCallback, context: BaseContext) -> None:
    await event.answer()
    await context.clear()
    await event.edit(text=texts.LINK_CANCELLED, attachments=[])


@router.message_callback(F.callback.payload == kb.MENU_LINK)
async def on_get_code(event: MessageCallback) -> None:
    """«Подключить Telegram» в «Моей анкете»: выдать код."""
    await event.answer()
    if not await repo.has_profile(event.callback.user.user_id):
        await event.edit(text=texts.NO_PROFILE, attachments=[])
        return
    if "tg" in await repo.profile_platforms(await repo.resolve_id(event.callback.user.user_id)):
        await event.edit(text="Telegram уже подключён к этой анкете ✅", attachments=kb.back_kb())
        return
    code, _ = await repo.create_link_code(event.callback.user.user_id)
    await event.edit(text=texts.LINK_CODE.format(code=code), attachments=kb.link_code_kb(code))

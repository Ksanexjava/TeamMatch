# bot/handlers/start.py
# Первый запуск, согласие на обработку данных, главное меню, /help, /cancel (зона Романа).

from maxapi import F
from maxapi.context.base import BaseContext
from maxapi.dispatcher import Router
from maxapi.filters.command import Command, CommandStart
from maxapi.types.updates.bot_started import BotStarted
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

from bot import keyboards as kb
from bot import texts
from bot.handlers.profile import start_form
from db import repo

router = Router(router_id="start")


async def _greet(user_id: int, answer) -> None:
    """Есть анкета → меню, нет → приветствие с согласием."""
    if await repo.has_profile(user_id):
        await answer(text=texts.MAIN_MENU, attachments=kb.main_menu_kb())
    else:
        await answer(text=texts.WELCOME, attachments=kb.consent_kb())


@router.bot_started()
async def on_bot_started(event: BotStarted, context: BaseContext) -> None:
    """Пользователь впервые открыл бота (кнопка «Начать»)."""
    await context.clear()

    async def answer(text, attachments):
        await event.bot.send_message(user_id=event.user.user_id, text=text, attachments=attachments)

    await _greet(event.user.user_id, answer)


@router.message_created(CommandStart())
async def on_start(event: MessageCreated, context: BaseContext) -> None:
    await context.clear()
    await _greet(event.message.sender.user_id, event.message.answer)


@router.message_created(Command("help"))
async def on_help(event: MessageCreated) -> None:
    await event.message.answer(texts.HELP)


@router.message_created(Command("cancel"))
async def on_cancel(event: MessageCreated, context: BaseContext) -> None:
    if await context.get_state() is None:
        await event.message.answer(texts.NOTHING_TO_CANCEL)
        return
    await context.clear()
    await event.message.answer(texts.CANCELLED)


@router.message_callback(F.callback.payload == kb.CONSENT_YES)
async def on_consent_yes(event: MessageCallback, context: BaseContext) -> None:
    await event.answer()
    user = event.callback.user
    await start_form(event.message.answer, context, max_username=user.username, first_name=user.first_name)


@router.message_callback(F.callback.payload == kb.CONSENT_NO)
async def on_consent_no(event: MessageCallback, context: BaseContext) -> None:
    await context.clear()
    await event.edit(text=texts.CONSENT_DECLINED, attachments=[])


@router.message_callback(F.callback.payload == kb.MENU_BACK)
async def on_menu_back(event: MessageCallback) -> None:
    await event.edit(text=texts.MAIN_MENU, attachments=kb.main_menu_kb())

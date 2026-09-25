# bot/handlers/fallback.py
# Подключается ПОСЛЕДНИМ: ловит всё, что не поймали другие обработчики.
# Нужен, чтобы бот не молчал на стикер, фото или текст не по сценарию.

from maxapi.context.base import BaseContext
from maxapi.dispatcher import Router
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

from bot import texts
from bot.states import ProfileForm

router = Router(router_id="fallback")

BUTTON_STEPS = {
    str(ProfileForm.degree), str(ProfileForm.degree_med), str(ProfileForm.course),
    str(ProfileForm.role), str(ProfileForm.looking_for), str(ProfileForm.confirm),
}


@router.message_created()
async def on_any_message(event: MessageCreated, context: BaseContext) -> None:
    state = await context.get_state()
    if state is None:
        await event.message.answer(texts.UNKNOWN)
    elif str(state) in BUTTON_STEPS:
        await event.message.answer(texts.USE_BUTTONS)
    else:
        await event.message.answer(texts.EMPTY_TEXT)


@router.message_callback()
async def on_any_callback(event: MessageCallback) -> None:
    # Старая кнопка из прошлого шага или после перезапуска — просто подтверждаем нажатие
    await event.answer(notification="Эта кнопка уже неактуальна. Напиши /start")

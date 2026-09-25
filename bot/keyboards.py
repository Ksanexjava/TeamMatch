# bot/keyboards.py
# Все inline-клавиатуры бота в одном месте.
# payload — строка, которую бот получает при нажатии кнопки (event.callback.payload).

from maxapi.types.attachments.buttons.callback_button import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from core.interests import LOOKING_FOR_OPTIONS

# Роли совпадают с ролями в тестовых анкетах Миши (tools/generate_test_profiles.py),
# иначе «разные роли» в матчинге будут считаться неправильно.
ROLES = ["разработка", "ML", "аналитика", "дизайн", "маркетинг", "финансы", "питчинг", "менеджмент"]
COURSES = ["1", "2", "3", "4", "5", "6"]

# ── payload-константы ────────────────────────────────────────────────────────
CONSENT_YES = "consent:yes"
CONSENT_NO = "consent:no"

MENU_FEED = "menu:feed"          # лента — зона Миши (bot/handlers/feed.py)
MENU_MATCHES = "menu:matches"    # мои мэтчи — зона Миши
MENU_PROFILE = "menu:profile"
MENU_EDIT = "menu:edit"
MENU_HIDE = "menu:hide"
MENU_SHOW = "menu:show"
MENU_DELETE = "menu:delete"
MENU_DELETE_CONFIRM = "menu:delete_confirm"
MENU_BACK = "menu:back"

# Кнопки ленты (зона Миши). К payload добавляется ":<user_id>" конкретной анкеты.
FEED_LIKE = "feed:like"   # лайкнуть
FEED_MSG = "feed:msg"     # лайкнуть с сообщением
FEED_SKIP = "feed:skip"   # пропустить
FEED_AGAIN = "feed:again" # лента закончилась → показать пропущенные анкеты снова

SKIP = "form:skip"
USE_MY_USERNAME = "form:use_username"
CONFIRM_SAVE = "form:save"
CONFIRM_RESTART = "form:restart"


def _markup(builder: InlineKeyboardBuilder) -> list:
    """Клавиатура в формате attachments=[...] для answer()/edit()."""
    return [builder.as_markup()]


def consent_kb() -> list:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Согласен(на), начнём", payload=CONSENT_YES))
    kb.row(CallbackButton(text="Нет, спасибо", payload=CONSENT_NO))
    return _markup(kb)


def main_menu_kb() -> list:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="🔍 Искать сокомандников", payload=MENU_FEED))
    kb.row(
        CallbackButton(text="🤝 Мои мэтчи", payload=MENU_MATCHES),
        CallbackButton(text="👤 Моя анкета", payload=MENU_PROFILE),
    )
    return _markup(kb)


def feed_card_kb(candidate_id: str) -> list:
    """Кнопки под карточкой в ленте: лайк / лайк+сообщение / пропустить (зона Миши)."""
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="👍 Лайк", payload=f"{FEED_LIKE}:{candidate_id}"),
        CallbackButton(text="💬 Лайк + сообщение", payload=f"{FEED_MSG}:{candidate_id}"),
    )
    kb.row(CallbackButton(text="👎 Пропустить", payload=f"{FEED_SKIP}:{candidate_id}"))
    kb.row(CallbackButton(text="← В меню", payload=MENU_BACK))
    return _markup(kb)


def feed_empty_kb() -> list:
    """Лента закончилась, но есть пропущенные анкеты: пройтись по ним ещё раз или в меню."""
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="🔄 Посмотреть пропущенные снова", payload=FEED_AGAIN))
    kb.row(CallbackButton(text="← В меню", payload=MENU_BACK))
    return _markup(kb)


def back_kb() -> list:
    """Одна кнопка «← В меню» (зона Миши)."""
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="← В меню", payload=MENU_BACK))
    return _markup(kb)


def after_match_kb() -> list:
    """После мэтча: продолжить листать ленту или вернуться в меню (зона Миши)."""
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="🔍 Смотреть дальше", payload=MENU_FEED))
    kb.row(CallbackButton(text="← В меню", payload=MENU_BACK))
    return _markup(kb)


def profile_kb(is_active: bool) -> list:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="✏️ Заполнить заново", payload=MENU_EDIT))
    if is_active:
        kb.row(CallbackButton(text="🙈 Скрыть анкету из поиска", payload=MENU_HIDE))
    else:
        kb.row(CallbackButton(text="👀 Снова показывать в поиске", payload=MENU_SHOW))
    kb.row(CallbackButton(text="🗑 Удалить мои данные", payload=MENU_DELETE))
    kb.row(CallbackButton(text="← В меню", payload=MENU_BACK))
    return _markup(kb)


def delete_confirm_kb() -> list:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Да, удалить всё", payload=MENU_DELETE_CONFIRM))
    kb.row(CallbackButton(text="Отмена", payload=MENU_PROFILE))
    return _markup(kb)


def course_kb() -> list:
    kb = InlineKeyboardBuilder()
    kb.row(*[CallbackButton(text=c, payload=f"course:{c}") for c in COURSES])
    kb.row(CallbackButton(text="Не студент / другое", payload=SKIP))
    return _markup(kb)


def role_kb() -> list:
    kb = InlineKeyboardBuilder()
    # по две кнопки в ряд; в payload — номер роли, чтобы не зависеть от текста
    for i in range(0, len(ROLES), 2):
        kb.row(*[CallbackButton(text=ROLES[j], payload=f"role:{j}") for j in range(i, min(i + 2, len(ROLES)))])
    return _markup(kb)


def looking_for_kb() -> list:
    kb = InlineKeyboardBuilder()
    for i, option in enumerate(LOOKING_FOR_OPTIONS):
        kb.row(CallbackButton(text=option.capitalize(), payload=f"goal:{i}"))
    return _markup(kb)


def skip_kb() -> list:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Пропустить", payload=SKIP))
    return _markup(kb)


def contact_kb(username: str | None) -> list:
    if not username:
        return []  # пустую клавиатуру не отправляем
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text=f"Использовать @{username}", payload=USE_MY_USERNAME))
    return _markup(kb)


def confirm_kb() -> list:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="✅ Сохранить", payload=CONFIRM_SAVE))
    kb.row(CallbackButton(text="🔄 Заполнить заново", payload=CONFIRM_RESTART))
    return _markup(kb)

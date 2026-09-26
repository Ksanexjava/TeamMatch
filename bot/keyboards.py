# bot/keyboards.py
# Все inline-клавиатуры бота в одном месте.
# payload — строка, которую бот получает при нажатии кнопки (event.callback.payload).

from maxapi.types.attachments.buttons.callback_button import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from core.interests import LOOKING_FOR_OPTIONS

ROLES = ["разработка", "ML", "аналитика", "дизайн", "маркетинг", "финансы", "питчинг", "менеджмент"]

DEGREES = [
    ("Бакалавриат", "бакалавриат", 4),
    ("Магистратура", "магистратура", 2),
    ("Специалитет", "специалитет", 5),
]
DEGREE_OTHER = "degree:other"

MED_DEGREES = [
    ("Специалитет (медицина)", "специалитет (медицина)", None),
    ("Ординатура", "ординатура", None),
]


CONSENT_YES = "consent:yes"
CONSENT_NO = "consent:no"

MENU_FEED = "menu:feed"        
MENU_MATCHES = "menu:matches"  
MENU_PROFILE = "menu:profile"
MENU_EDIT = "menu:edit"              # заполнить анкету заново
MENU_EDIT_FIELDS = "menu:edit_fields"  # редактировать отдельные поля
MENU_REPORT = "menu:report"          # пожаловаться
EDIT_FIELD = "edit"               
MENU_HIDE = "menu:hide"
MENU_SHOW = "menu:show"
MENU_DELETE = "menu:delete"
MENU_DELETE_CONFIRM = "menu:delete_confirm"
MENU_BACK = "menu:back"


FEED_LIKE = "feed:like"   # лайкнуть
FEED_MSG = "feed:msg"     # лайкнуть с сообщением
FEED_SKIP = "feed:skip"   # пропустить
FEED_AGAIN = "feed:again" # лента закончилась

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
    kb.row(CallbackButton(text="⚠️ Пожаловаться", payload=MENU_REPORT))
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
    kb.row(CallbackButton(text="✏️ Редактировать анкету", payload=MENU_EDIT_FIELDS))
    kb.row(CallbackButton(text="🔄 Заполнить заново", payload=MENU_EDIT))
    if is_active:
        kb.row(CallbackButton(text="🙈 Скрыть анкету из поиска", payload=MENU_HIDE))
    else:
        kb.row(CallbackButton(text="👀 Снова показывать в поиске", payload=MENU_SHOW))
    kb.row(CallbackButton(text="🗑 Удалить мои данные", payload=MENU_DELETE))
    kb.row(CallbackButton(text="← В меню", payload=MENU_BACK))
    return _markup(kb)



EDIT_FIELDS = [
    ("name", "Имя"), ("photo", "Фото"),
    ("university", "Вуз"), ("education", "Уровень и курс"),
    ("direction", "Направление"), ("city", "Город"),
    ("role", "Роль"), ("looking_for", "Что ищу"),
    ("interests", "Интересы"), ("about", "О себе"),
    ("github", "GitHub"), ("contact", "Контакт"),
]


def edit_fields_kb() -> list:
    """Выбор поля для редактирования — по две кнопки в ряд."""
    kb = InlineKeyboardBuilder()
    for i in range(0, len(EDIT_FIELDS), 2):
        kb.row(*[
            CallbackButton(text=label, payload=f"{EDIT_FIELD}:{key}")
            for key, label in EDIT_FIELDS[i:i + 2]
        ])
    kb.row(CallbackButton(text="← Назад к анкете", payload=MENU_PROFILE))
    return _markup(kb)


def delete_confirm_kb() -> list:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Да, удалить всё", payload=MENU_DELETE_CONFIRM))
    kb.row(CallbackButton(text="Отмена", payload=MENU_PROFILE))
    return _markup(kb)


def degree_kb() -> list:
    """Уровень образования. В payload — номер варианта из DEGREES."""
    kb = InlineKeyboardBuilder()
    for i, (label, _, _) in enumerate(DEGREES):
        kb.row(CallbackButton(text=label, payload=f"degree:{i}"))
    kb.row(CallbackButton(text="Другое (медицина)", payload=DEGREE_OTHER))
    return _markup(kb)


def degree_med_kb() -> list:
    """Для «Другое»: специалитет или ординатура. В payload — номер варианта из MED_DEGREES."""
    kb = InlineKeyboardBuilder()
    for i, (label, _, _) in enumerate(MED_DEGREES):
        kb.row(CallbackButton(text=label, payload=f"degmed:{i}"))
    return _markup(kb)


def course_kb(max_courses: int) -> list:
    """Кнопки курсов от 1 до max_courses (бакалавриат — 4, магистратура — 2, специалитет — 5)."""
    kb = InlineKeyboardBuilder()
    kb.row(*[CallbackButton(text=str(c), payload=f"course:{c}") for c in range(1, max_courses + 1)])
    return _markup(kb)


def role_kb() -> list:
    kb = InlineKeyboardBuilder()
  
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
        return [] 
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text=f"Использовать @{username}", payload=USE_MY_USERNAME))
    return _markup(kb)


def confirm_kb() -> list:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="✅ Сохранить", payload=CONFIRM_SAVE))
    kb.row(CallbackButton(text="🔄 Заполнить заново", payload=CONFIRM_RESTART))
    return _markup(kb)

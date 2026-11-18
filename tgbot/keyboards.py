"""Инлайн-клавиатуры Telegram-бота. Коды кнопок совпадают с ботом MAX там, где смысл тот же."""

from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards import DEGREES, MED_DEGREES, ROLES, SEARCH_MODES
from config import LAW_152_URL, settings
from core.interests import LOOKING_FOR_OPTIONS

CONSENT_YES = "consent:yes"
CONSENT_NO = "consent:no"

MENU_FEED = "menu:feed"
MENU_MATCHES = "menu:matches"
MENU_PROFILE = "menu:profile"
MENU_SETTINGS = "menu:settings"
MENU_REPORT = "menu:report"
MENU_BACK = "menu:back"
MENU_START = "menu:start"
MENU_EDIT = "menu:edit"                 # заполнить заново
MENU_EDIT_FIELDS = "menu:edit_fields"   # выбрать поле
EDIT_FIELD = "edit"                     # edit:<поле>
MENU_HIDE = "menu:hide"
MENU_SHOW = "menu:show"
MENU_DELETE = "menu:delete"
MENU_DELETE_CONFIRM = "menu:delete_confirm"
MENU_LINK = "menu:link"

FEED_LIKE = "feed:like"
FEED_MSG = "feed:msg"
FEED_SKIP = "feed:skip"
FEED_AGAIN = "feed:again"
FEED_NEXT = "feed:next"
SEARCH_MODE = "search:mode"

FORM_SKIP = "form:skip"
FORM_USE_USERNAME = "form:use_username"
FORM_SAVE = "form:save"
FORM_SAVE_FORCE = "form:save_force"
FORM_RESTART = "form:restart"

LINK_START = "link:start"
LINK_REPLACE = "link:replace"
LINK_CANCEL = "link:cancel"

EDIT_FIELDS = [
    ("name", "Имя"), ("photo", "Фото"),
    ("university", "Вуз"), ("education", "Уровень и курс"),
    ("direction", "Направление"), ("city", "Город"),
    ("role", "Роль"), ("looking_for", "Что ищу"),
    ("interests", "Интересы"), ("about", "О себе"),
    ("github", "GitHub"), ("username", "Контакт"),
]


def _kb(*rows: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for row in rows:
        b.row(*row)
    return b.as_markup()


def _btn(text: str, data: str):
    from aiogram.types import InlineKeyboardButton
    return InlineKeyboardButton(text=text, callback_data=data)


def _url(text: str, url: str):
    from aiogram.types import InlineKeyboardButton
    return InlineKeyboardButton(text=text, url=url)


def _app_row() -> list:
    """Кнопка мини-приложения — только если оно подключено (WEBAPP_URL)."""
    from aiogram.types import InlineKeyboardButton
    if not settings.webapp_url:
        return []
    return [InlineKeyboardButton(text="📱 Открыть приложение", web_app=WebAppInfo(url=settings.webapp_url + "/"))]


def consent_kb() -> InlineKeyboardMarkup:
    rows = [[_btn("✅ Согласен(на), начнём", CONSENT_YES)]]
    if settings.consent_url:
        rows.append([_url("📄 Согласие", settings.consent_url), _url("🔒 Политика", settings.privacy_url)])
    rows.append([_url("⚖️ Закон 152-ФЗ", LAW_152_URL)])
    rows.append([_btn("🔗 Уже есть анкета в MAX", LINK_START)])
    rows.append([_btn("Нет, спасибо", CONSENT_NO)])
    return _kb(*rows)


def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [_btn("🔍 Искать сокомандников", MENU_FEED)],
        [_btn("🤝 Мои мэтчи", MENU_MATCHES), _btn("👤 Моя анкета", MENU_PROFILE)],
        [_btn("⚙️ Настройки поиска", MENU_SETTINGS)],
        [_btn("⚠️ Пожаловаться", MENU_REPORT)],
    ]
    if _app_row():
        rows.insert(1, _app_row())
    return _kb(*rows)


def feed_card_kb(candidate_id: str) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("👍 Лайк", f"{FEED_LIKE}:{candidate_id}"), _btn("💬 Лайк + сообщение", f"{FEED_MSG}:{candidate_id}")],
        [_btn("👎 Пропустить", f"{FEED_SKIP}:{candidate_id}")],
        [_btn("← В меню", MENU_BACK)],
    )


def feed_empty_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("🔄 Посмотреть пропущенные снова", FEED_AGAIN)], [_btn("← В меню", MENU_BACK)])


def after_match_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("🔍 Смотреть дальше", FEED_NEXT)], [_btn("← В меню", MENU_BACK)])


def search_settings_kb(current: str) -> InlineKeyboardMarkup:
    rows = [[_btn(("✅ " if current == mode else "") + label, f"{SEARCH_MODE}:{mode}")] for mode, label in SEARCH_MODES]
    rows.append([_btn("🔍 Открыть ленту", MENU_FEED)])
    rows.append([_btn("← В меню", MENU_BACK)])
    return _kb(*rows)


def settings_hint_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("⚙️ Настройки поиска", MENU_SETTINGS)], [_btn("← В меню", MENU_BACK)])


def back_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("← В меню", MENU_BACK)])


def profile_kb(is_active: bool, max_linked: bool) -> InlineKeyboardMarkup:
    rows = [
        [_btn("✏️ Редактировать анкету", MENU_EDIT_FIELDS)],
        [_btn("🔄 Заполнить заново", MENU_EDIT)],
        [_btn("🙈 Скрыть анкету из поиска", MENU_HIDE) if is_active else _btn("👀 Снова показывать в поиске", MENU_SHOW)],
    ]
    if not max_linked:
        rows.append([_btn("🔗 Подключить MAX", MENU_LINK)])
    rows.append([_btn("🗑 Удалить мои данные", MENU_DELETE)])
    rows.append([_btn("← В меню", MENU_BACK)])
    return _kb(*rows)


def edit_fields_kb() -> InlineKeyboardMarkup:
    rows = [[_btn(label, f"{EDIT_FIELD}:{key}") for key, label in EDIT_FIELDS[i:i + 2]] for i in range(0, len(EDIT_FIELDS), 2)]
    rows.append([_btn("← Назад к анкете", MENU_PROFILE)])
    return _kb(*rows)


def delete_confirm_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("Да, удалить всё", MENU_DELETE_CONFIRM)], [_btn("Отмена", MENU_PROFILE)])


def start_again_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("🚀 Начать заново", MENU_START)])


def degree_kb() -> InlineKeyboardMarkup:
    rows = [[_btn(label, f"deg:{i}")] for i, (label, _, _) in enumerate(DEGREES)]
    rows.append([_btn("Другое (медицина)", "deg:other")])
    return _kb(*rows)


def degree_med_kb() -> InlineKeyboardMarkup:
    return _kb(*[[_btn(label, f"degmed:{i}")] for i, (label, _, _) in enumerate(MED_DEGREES)])


def course_kb(max_courses: int) -> InlineKeyboardMarkup:
    return _kb([_btn(str(c), f"course:{c}") for c in range(1, max_courses + 1)])


def role_kb() -> InlineKeyboardMarkup:
    return _kb(*[[_btn(ROLES[j], f"role:{j}") for j in range(i, min(i + 2, len(ROLES)))] for i in range(0, len(ROLES), 2)])


def looking_for_kb() -> InlineKeyboardMarkup:
    return _kb(*[[_btn(option.capitalize(), f"goal:{i}")] for i, option in enumerate(LOOKING_FOR_OPTIONS)])


def skip_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("Пропустить", FORM_SKIP)])


def contact_kb(username: str | None) -> InlineKeyboardMarkup | None:
    return _kb([_btn(f"Использовать @{username}", FORM_USE_USERNAME)]) if username else None


def confirm_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("✅ Сохранить", FORM_SAVE)], [_btn("🔄 Заполнить заново", FORM_RESTART)])


def duplicate_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("🔗 Ввести код из MAX", LINK_START)], [_btn("Это не я — сохранить анкету", FORM_SAVE_FORCE)])


def link_cancel_kb() -> InlineKeyboardMarkup:
    return _kb([_btn("Отмена", LINK_CANCEL)])


def link_replace_kb(code: str) -> InlineKeyboardMarkup:
    return _kb([_btn("Удалить анкету здесь и подключить", f"{LINK_REPLACE}:{code}")], [_btn("Отмена", LINK_CANCEL)])


def link_code_kb(code: str) -> InlineKeyboardMarkup:
    rows = []
    if settings.max_bot_username:
        rows.append([_url("Открыть Тиммейт в MAX", f"https://max.ru/{settings.max_bot_username}?start=link-{code}")])
    rows.append([_btn("← Назад к анкете", MENU_PROFILE)])
    return _kb(*rows)


def as_dict(markup: InlineKeyboardMarkup) -> dict:
    """Клавиатура в виде JSON для messengers/telegram.py (уведомления из других процессов)."""
    return markup.model_dump(exclude_none=True)

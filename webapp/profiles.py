"""Проверка анкеты из мини-приложения и её представление для клиента.

Правила те же, что у бота (bot/handlers/profile.py): лимиты длины, фильтр мата,
запрет ссылок, GitHub только ссылкой на GitHub, контакт без ссылок на сайты.
"""

from bot.keyboards import DEGREES, MED_DEGREES, ROLES
from core.interests import LOOKING_FOR_OPTIONS, normalize_interests
from core.moderation import has_ads, is_clean, is_valid_contact, normalize_github
from messengers import ids

LIMITS = {
    "name": 50, "university": 100, "direction": 100, "city": 60,
    "about": 500, "github": 200, "username": 100,
}
MESSAGE_LIMIT = 300

# Уровень образования → максимальный курс (None у медицины — до 10, как в боте).
DEGREE_MAX_COURSE = {value: max_course or 10 for _, value, max_course in DEGREES + MED_DEGREES}

BANNED = "Без мата, оскорблений и экстремизма, пожалуйста"
NO_LINKS = "Ссылки здесь нельзя — это защита от рекламы"


def options() -> dict:
    return {
        "roles": ROLES,
        "looking_for": LOOKING_FOR_OPTIONS,
        "degrees": [
            {"label": label, "value": value, "max_course": DEGREE_MAX_COURSE[value]}
            for label, value, _ in DEGREES + MED_DEGREES
        ],
        "limits": {**LIMITS, "message": MESSAGE_LIMIT},
    }


def _text(data: dict, field: str, errors: dict, required: bool = True) -> str:
    value = str(data.get(field) or "").strip()
    if not value:
        if required:
            errors[field] = "Заполни это поле"
        return ""
    if len(value) > LIMITS[field]:
        errors[field] = f"Не длиннее {LIMITS[field]} символов"
    elif not is_clean(value):
        errors[field] = BANNED
    elif field not in ("username", "github") and has_ads(value):
        errors[field] = NO_LINKS
    return value


def validate_profile(data: dict) -> tuple[dict, dict]:
    """Сырые данные формы → (чистая анкета, ошибки по полям)."""
    errors: dict[str, str] = {}
    clean: dict = {}

    for field in ("name", "university", "direction", "city"):
        clean[field] = _text(data, field, errors)
    clean["about"] = _text(data, "about", errors, required=False)

    degree = str(data.get("degree") or "")
    if degree not in DEGREE_MAX_COURSE:
        errors["degree"] = "Выбери уровень образования"
    clean["degree"] = degree

    try:
        course = int(data.get("course"))
    except (TypeError, ValueError):
        course = 0
    if not 1 <= course <= DEGREE_MAX_COURSE.get(degree, 10):
        errors["course"] = "Выбери курс"
    clean["course"] = course or None

    role = str(data.get("role") or "")
    if role not in ROLES:
        errors["role"] = "Выбери роль"
    clean["role"] = role

    goal = str(data.get("looking_for") or "")
    if goal not in LOOKING_FOR_OPTIONS:
        errors["looking_for"] = "Выбери, для чего ищешь команду"
    clean["looking_for"] = goal

    raw_interests = data.get("interests") or []
    if isinstance(raw_interests, str):
        raw_interests = [raw_interests]
    joined = ", ".join(str(x) for x in raw_interests)
    if not is_clean(joined):
        errors["interests"] = BANNED
    elif has_ads(joined):
        errors["interests"] = NO_LINKS
    clean["interests"] = normalize_interests(joined)
    if not clean["interests"] and "interests" not in errors:
        errors["interests"] = "Добавь хотя бы один интерес"

    github = str(data.get("github") or "").strip()
    if github:
        normalized = normalize_github(github)
        if normalized is None or len(normalized) > LIMITS["github"]:
            errors["github"] = "Только ник или ссылка вида github.com/username"
        github = normalized or github
    clean["github"] = github

    contact = _text(data, "username", errors)
    if contact and "username" not in errors and not is_valid_contact(contact):
        errors["username"] = "Ник (@username), телефон или e-mail — без ссылок на сайты"
    clean["username"] = contact

    return clean, errors


def validate_message(text: str) -> tuple[str, str | None]:
    value = (text or "").strip()
    if len(value) > MESSAGE_LIMIT:
        return value, f"Не длиннее {MESSAGE_LIMIT} символов"
    if value and not is_clean(value):
        return value, BANNED
    if value and has_ads(value):
        return value, "Ссылки в сообщениях нельзя — контакты придут обоим при мэтче"
    return value, None


def photo_url(profile: dict) -> str:
    """Фото, загруженное через мини-приложение (web:<файл>). Фото из MAX — токен вложения,
    в браузере его не показать, поэтому для них клиент рисует аватар с инициалами."""
    photo = profile.get("photo") or ""
    return f"/media/{photo[4:]}" if photo.startswith("web:") else ""


def card(profile: dict, *, contact: bool = False) -> dict:
    """Анкета для клиента. Контакт — только своей анкете и при мэтче."""
    result = {
        "id": profile["user_id"],
        "name": profile.get("name") or "Без имени",
        "university": profile.get("university") or "",
        "degree": profile.get("degree") or "",
        "course": profile.get("course"),
        "direction": profile.get("direction") or "",
        "city": profile.get("city") or "",
        "role": profile.get("role") or "",
        "looking_for": profile.get("looking_for") or "",
        "interests": list(profile.get("interests") or []),
        "about": profile.get("about") or "",
        "github": profile.get("github") or "",
        "photo_url": photo_url(profile),
        "platform": ids.platform_of(profile["user_id"]),
        "is_test": bool(profile.get("is_test")),
    }
    if contact:
        result["contact"] = profile.get("username") or ""
    return result

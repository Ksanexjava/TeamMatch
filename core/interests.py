# core/interests.py
# Нормализация интересов (зона Романа).
# Пользователь пишет интересы свободным текстом через запятую:
#   "Python, ML ,  хак, Figma"
# а в базу и в матчинг (core/matching.py) уходит аккуратный список (регистр как у человека):
#   ["Python", "ML", "хакатон", "Figma"]
# Чистые функции: без базы и без сети — легко тестировать (tests/test_interests.py).

import re

# Синонимы: разные написания одного и того же → одно каноническое слово.
# Добавлять новые пары можно смело: ключ — как пишут люди, значение — как храним.
SYNONYMS = {
    # форматы активностей
    "хак": "хакатон",
    "хакатоны": "хакатон",
    "hackathon": "хакатон",
    "олимп": "олимпиада",
    "олимпиады": "олимпиада",
    "кейс": "кейс-чемпионат",
    "кейсы": "кейс-чемпионат",
    "кейс чемпионат": "кейс-чемпионат",
    "кейс-чемпионаты": "кейс-чемпионат",
    # направления
    "машинное обучение": "ml",
    "machine learning": "ml",
    "мл": "ml",
    "ai": "нейросети",
    "ии": "нейросети",
    "нейронки": "нейросети",
    "питон": "python",
    "бэкенд": "backend",
    "бекенд": "backend",
    "фронтенд": "frontend",
    "фронт": "frontend",
    "аналитика данных": "аналитика",
    "data science": "данные",
    "ux/ui": "ui",
    "ui/ux": "ui",
    "фигма": "figma",
    "бд": "базы данных",
    "sql базы": "sql",
}

# Кнопки быстрого выбора цели (поле looking_for у Миши).
LOOKING_FOR_OPTIONS = ["хакатон", "кейс-чемпионат", "олимпиада", "стартап"]

MAX_INTERESTS = 10       # больше — уже шум
MAX_INTEREST_LEN = 40    # защита от «простыни» вместо интереса


def normalize_one(raw: str) -> str:
    """Один интерес: нижний регистр, без лишних пробелов и кавычек, с учётом синонимов."""
    text = (raw or "").strip().lower().replace("ё", "е")
    text = text.strip(" .!?\"'«»#")
    text = re.sub(r"\s+", " ", text)
    return SYNONYMS.get(text, text)


def _display(raw: str, key: str) -> str:
    """Как показывать интерес: так, как написал человек («Python», «Цифровой прорыв»).

    Если сработал синоним («питон» → «python»), показываем каноническое слово.
    """
    text = re.sub(r"\s+", " ", (raw or "").strip().strip(" .!?\"'«»#"))
    if text.lower().replace("ё", "е") != key:
        return key
    return text


def normalize_interests(raw_text: str) -> list[str]:
    """Строка от пользователя → список интересов без повторов (порядок сохраняется).

    Регистр сохраняется как у пользователя: «Python, ML» → ["Python", "ML"].
    Повторы ищутся без учёта регистра и синонимов: «python, Python, питон» → ["python"].
    Подбор (core/matching.py) сравнивает интересы без учёта регистра, так что это не мешает.
    Разделители: запятая, точка с запятой, перенос строки.
    Пустые и слишком длинные куски отбрасываются.
    """
    parts = re.split(r"[,;\n]+", raw_text or "")
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = normalize_one(part)
        if not key or len(key) > MAX_INTEREST_LEN:
            continue
        if key not in seen:
            seen.add(key)
            result.append(_display(part, key))
        if len(result) >= MAX_INTERESTS:
            break
    return result

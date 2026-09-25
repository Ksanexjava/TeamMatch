# tests/test_interests.py
# Запуск: python -m pytest -q

from core.interests import normalize_interests, normalize_one


def test_lowercase_and_trim():
    assert normalize_interests("  Python , ML ") == ["python", "ml"]


def test_synonyms():
    assert normalize_interests("хак, Олимп, машинное обучение, питон") == ["хакатон", "олимпиада", "ml", "python"]


def test_duplicates_removed_order_kept():
    assert normalize_interests("python, Python, питон, ml") == ["python", "ml"]


def test_separators_and_empty_parts():
    assert normalize_interests("sql;; excel\nfigma,,") == ["sql", "excel", "figma"]


def test_limits():
    assert normalize_interests("а" * 100) == []
    assert len(normalize_interests(",".join(f"тема{i}" for i in range(30)))) == 10


def test_yo_and_quotes():
    assert normalize_one("«Ёлка»") == "елка"


def test_matches_misha_format():
    """Нормализованные интересы совпадают с тестовыми анкетами → матчинг Миши их видит."""
    from core.matching import shared_interests

    me = {"interests": normalize_interests("Python, Аналитика")}
    other = {"interests": ["ml", "python", "аналитика"]}
    assert shared_interests(me, other) == {"python", "аналитика"}

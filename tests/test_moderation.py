# tests/test_moderation.py
import pytest

from core.moderation import find_banned, has_ads, is_clean, is_valid_contact, normalize_github

# ── Мат, оскорбления, экстремизм ─────────────────────────────────────────────

BAD = [
    # мат (кириллица)
    "хуй", "Похуй на всё", "нахуя", "ОХУЕЛ", "пизда", "распиздяй", "заебал", "ебать", "уебок",
    "съебался", "блядь", "бля", "блять", "сука", "суки", "сука!", "сучка", "мудак", "гандон",
    "пидор", "пидр", "шлюха", "залупа", "чмо", "говно", "долбоёб", "ебанутый", "шалава",
    # маскировка: латиница, цифры, символы, пробелы
    "xyй", "хууууй", "пиздa", "3аебал", "ху*й", "х у й", "х.у.й", "з а л у п а", "xyйня",
    "eбaть", "п1зда",
    # транслит и смесь алфавитов
    "Zalupaсибирск", "zalupa", "ZALUPA", "huy", "nahuy", "pizdec", "blyat", "suka", "cyka",
    "ebat", "dolboeb", "Новохуйск",
    # английский мат
    "fuck", "FUCKING", "shit", "bullshit", "bitch",
    # расизм и национальные оскорбления
    "ниггер", "nigger", "хачи", "чурки", "жиды", "хохлы", "пиндосы", "черножопый", "узкоглазые",
    # экстремизм
    "Слава Гитлеру", "зиг хайль", "Sieg Heil", "white power", "1488", "14/88", "卐",
    "АУЕ", "колумбайн", "ИГИЛ",
    # слова из data/banwords.txt
    "казино", "Ставки на спорт",
]

GOOD = [
    # похожие на мат, но нормальные слова
    "страхует", "застрахуй", "не психуй", "употребление", "небо", "небанальный", "обед", "себе",
    "себя", "хулиган", "похудеть", "хуже", "бледный", "бляха", "сукно", "сук дерева", "мудрый",
    "педикюр", "чмокнуть", "хлеб", "учеба", "Глеб", "ребус", "хутор", "сражение", "сравнение",
    "мандарин", "мандат", "херувим", "оскорблять", "потреблять", "корабль", "рубля", "ребята",
    "плохую", "втихую", "долбануть", "дебилитирующий",
    # похожие на экстремистские, но нормальные слова
    "хачапури", "жидкость", "жидкий азот", "Нигерия", "Нигер", "зигзаг", "хохолок", "хохлома",
    "Москалёв", "укроп", "даунтаун", "сучковатый",
    # английские слова, которые в транслите похожи на мат
    "jobs", "eyeball", "ebook", "eBay", "Hyundai", "Huawei", "Xue Li", "sherpa", "played",
    "yamashita", "hydrochloric", "debug", "gown",
    # обычная анкета
    "Python, ML, аналитика", "Люблю хакатоны и олимпиады по программированию", "НГТУ НЭТИ",
    "Новосибирск", "@user001", "https://github.com/user001", "Потребление энергии",
    "Хочу в команду на Цифровой прорыв 2026", "кейс-чемпионат", "Разработчик игр (Unity, C#)",
    "+7 913 148 88 11", "14 лет опыта",
]


@pytest.mark.parametrize("text", BAD)
def test_bad_detected(text):
    assert not is_clean(text), text


@pytest.mark.parametrize("text", GOOD)
def test_good_passes(text):
    assert is_clean(text), (text, find_banned(text))


# ── Реклама ──────────────────────────────────────────────────────────────────

ADS = [
    "https://casino.ru", "заходи на vk.com/mygroup", "t.me/channel", "www.example", "site.ru",
    "site . ru", "site точка ру", "site(dot)com",
    "mysite.online", "tg://resolve", "http :// x",
]
NO_ADS = [
    "Люблю Python. So I code", "ASP.NET и Socket.IO", "Node.js, Vue.js", "НГТУ. Работаю с 2024",
    "C# / .NET", "Файл main.py, deploy.sh", "Т. к. я backend", "Python, ML, аналитика",
    "Пиши в ТГ @ivan_petrov", "vk: @id12345", "почта ivan@mail.ru",
]


@pytest.mark.parametrize("text", ADS)
def test_ads_detected(text):
    assert has_ads(text), text


@pytest.mark.parametrize("text", NO_ADS)
def test_no_ads_passes(text):
    assert not has_ads(text), text


# ── GitHub и контакт ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("text, expected", [
    ("user001", "https://github.com/user001"),
    ("@user001", "https://github.com/user001"),
    ("github.com/user001", "https://github.com/user001"),
    ("https://www.github.com/User-1/repo/", "https://github.com/User-1/repo"),
    ("https://gitlab.com/user", None),
    ("vk.com/user", None),
    ("https://casino.ru", None),
    ("нет", None),
    ("my portfolio", None),
])
def test_normalize_github(text, expected):
    assert normalize_github(text) == expected


@pytest.mark.parametrize("text", [
    "@ivan_petrov", "ivan_petrov", "+7 913 123-45-67", "89131234567", "ivan@mail.ru",
    "ТГ: @ivan, VK: @ivan", "Иван", "пиши в личку @ivan или на ivan@mail.ru",
])
def test_contact_ok(text):
    assert is_valid_contact(text)


@pytest.mark.parametrize("text", ["t.me/ivan", "https://t.me/ivan", "vk.com/ivan", "ivan.ru", "мой сайт ivan точка ру"])
def test_contact_rejected(text):
    assert not is_valid_contact(text)


def test_test_profiles_are_clean():
    """40 тестовых анкет не должны задевать фильтр."""
    import json
    from pathlib import Path

    profiles = json.loads((Path(__file__).parent.parent / "data" / "test_profiles.json").read_text("utf-8"))
    for p in profiles:
        for field in ("name", "university", "city", "about"):
            if p.get(field):
                assert is_clean(p[field]) and not has_ads(p[field]), (field, p[field])
        for interest in p.get("interests", []):
            assert is_clean(interest) and not has_ads(interest), interest
        assert is_valid_contact(p["username"]), p["username"]
        if p.get("github"):
            assert normalize_github(p["github"]) == p["github"], p["github"]

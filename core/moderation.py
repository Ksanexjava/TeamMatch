# core/moderation.py
# Модерация текстов анкеты и сообщений: мат, оскорбления, расистские и экстремистские
# слова, реклама (ссылки на сторонние сайты). Чистые функции: без базы и без сети.
# Тесты — tests/test_moderation.py.
#
# Как работает проверка слов:
#   1. Текст режется на слова. Внутри слова выкидываются «маскирующие» символы
#      (ху*й, х_у_й, з-а-л-у-п-а), а буквы, написанные через пробел (х у й), склеиваются.
#   2. Каждое слово проверяется в нескольких вариантах написания:
#        • «визуальный»  — латиница/цифры, похожие на кириллицу: xyй → хуй, 3аебал → заебал;
#        • «транслит»    — латиница по звучанию: Zalupa → залупа, pizdec → пиздец, huy → хуй.
#      Слова вида «Zalupaсибирск» (смесь алфавитов) тоже ловятся через транслит.
#   3. Варианты проверяются регулярками по КОРНЯМ (с учётом приставок) — так ловятся
#      «похуй» и «заебал», но не «страхует», «небо», «хачапури», «жидкость», «Нигерия».
#   4. Плюс точные слова из data/banwords.txt — команда может дописывать туда свои.
#
# Реклама: в текстовых полях ссылки запрещены совсем (включая «site точка ru», t.me,
# @каналы). Единственная разрешённая ссылка — GitHub, и только в поле GitHub
# (см. normalize_github).
#
# Фильтр не идеален (и не должен быть): цель — отсечь очевидный мусор в MVP.

import re
from functools import lru_cache
from pathlib import Path

EXTRA_WORDS_PATH = Path(__file__).resolve().parent.parent / "data" / "banwords.txt"

# ── Нормализация ─────────────────────────────────────────────────────────────

# Латиница и цифры, ПОХОЖИЕ на кириллицу внешне: xyй, 3аебал, п1зда
_VISUAL = str.maketrans({
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к", "m": "м", "o": "о",
    "p": "р", "t": "т", "x": "х", "y": "у", "u": "и", "r": "г", "n": "п",
    "0": "о", "3": "з", "4": "ч", "6": "б", "1": "и", "!": "и", "@": "а", "$": "с",
})

# Латиница ПО ЗВУЧАНИЮ (транслит): сначала буквосочетания, потом одиночные буквы
_TRANSLIT_MULTI = [
    ("shch", "щ"), ("sch", "щ"), ("zh", "ж"), ("kh", "х"), ("ch", "ч"), ("sh", "ш"),
    ("ts", "ц"), ("ya", "я"), ("ja", "я"), ("yu", "ю"), ("ju", "ю"), ("yo", "е"),
    ("iy", "ий"), ("yi", "ый"),
]
_TRANSLIT_ONE = str.maketrans({
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "х",
    "i": "и", "j": "й", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п",
    "q": "к", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "х",
    "y": "й", "z": "з",
    "0": "о", "3": "з", "4": "ч", "6": "б", "1": "и", "!": "и", "@": "а", "$": "с",
})

# Английские слова, которые в транслите случайно похожи на мат (ebook → «ебоок»)
_LATIN_SAFE = {
    "ebook", "ebooks", "ebay", "ebpf", "ebitda", "ebola", "hue", "hues", "huey", "hui",
    "huawei", "hyundai", "sukhoi", "mudra", "bleach", "xue", "suki", "gown", "gowns",
    "ebony", "eben", "ebb", "ebbs", "ebbing", "ebba", "ebert", "ebenezer", "zig", "hachi", "negra", "niger",
    "aye", "manda", "huerta", "huygens", "huevos", "huer", "zigzag",
}

# Символы, которыми маскируют мат внутри слова: ху*й, х_у_й, п.и.з.д.а
_MASK_CHARS = re.compile(r"[*_\-.,'`~^#%&+=|\"«»]+")
# Разделители слов
_SPLIT = re.compile(r"[\s:;/\\()\[\]{}<>?]+")


def _squash_repeats(word: str) -> str:
    """хууууй → хуй, сууука → сука."""
    return re.sub(r"(.)\1+", r"\1", word)


def _translit(word: str) -> str:
    for src, dst in _TRANSLIT_MULTI:
        word = word.replace(src, dst)
    return word.translate(_TRANSLIT_ONE)


def _chunks(text: str) -> list[str]:
    """Текст → «сырые» слова. Буквы через пробел (х у й, з а л у п а) склеиваются."""
    raw = [c for c in _SPLIT.split(text.lower().replace("ё", "е")) if c]
    result: list[str] = []
    singles: list[str] = []
    for chunk in raw:
        bare = _MASK_CHARS.sub("", chunk)
        if len(bare) == 1:
            singles.append(bare)
            continue
        if len(singles) >= 3:
            result.append("".join(singles))
        elif singles:
            result.extend(singles)
        singles = []
        result.append(chunk)
    if len(singles) >= 3:
        result.append("".join(singles))
    else:
        result.extend(singles)
    return result


def normalize_text(text: str) -> list[str]:
    """Текст → список слов-кандидатов (все варианты написания) для проверки."""
    words: list[str] = []
    for chunk in _chunks(text or ""):
        # Вариант без маскирующих символов и вариант «как есть» (кусками между ними)
        chunk = chunk.strip("!")   # «сука!» — восклицательный знак в конце не буква «и»
        pieces = {_MASK_CHARS.sub("", chunk)} | set(_MASK_CHARS.split(chunk))
        for piece in pieces:
            if not piece:
                continue
            if piece in _LATIN_SAFE:
                continue
            variants = []
            visual = piece.translate(_VISUAL)
            if not re.search(r"[a-z]", visual):
                # визуальная замена имеет смысл, только если все буквы стали кириллицей
                variants.append(visual)
            variants.append(_translit(piece))
            for variant in variants:
                for word in re.findall(r"[а-я]+", variant):
                    words.append(word)
                    words.append(_squash_repeats(word))
    # без повторов, порядок сохраняем
    return list(dict.fromkeys(words))


# ── Запрещённые слова ────────────────────────────────────────────────────────

# приставки, с которыми часто встречаются корни
_PREFIX = r"(?:по|на|ни|за|от|до|вы|у|о|об|раз|рас|с|съ|под|при|пере|недо|про|вз|вс|из|ис)?"
# для корня «еб» без «с»: иначе ловятся «себе», «себя»
_PREFIX_EB = r"(?:по|на|ни|за|от|до|вы|у|о|раз|рас|под|при|пере|недо|про|долбо|вз|из)?"

# Мат и грубые оскорбления. Регулярки применяются к КАЖДОМУ отдельному слову.
_PROFANITY = [
    rf"^{_PREFIX}ху[йеяюи]",            # хуй, похуй, нахуя, охуел (но не «страхует», «хулиган»)
    r"(?<!стра)(?<!штри)(?<!пси)(?<!пло)ху(?:й|е[вс])",   # Новохуйск — корень внутри слова (но не «страхуй», «психуй»)
    r"долбо[её]б",
    r"пизд",                             # пизд* в любом месте слова
    r"^пизж",                            # пиздеж → пизжу
    rf"^{_PREFIX_EB}еб(?:а|у|л|н|ш|и|е|о|с|к|ц|ыв)",   # ебать, заебал, уебок, долбоеб (но не «небо»)
    rf"^{_PREFIX}ъеб",                   # съебал, подъебка
    r"бляд",                             # блядь, выблядок (но не «бледный»)
    r"^бля(?:т|ть|ха-муха)?$",           # «бля», «блять» — но не «употребление», «бляха»
    r"^сук(?:а|и|у|ой|ам|ами|ах|ин|ина|ины|ину|ины)$",  # сука, сукин (но не «сук», «сукно»)
    r"^суч(?:ка|ки|ке|ку|кой|ками|ках|ара|ары|аре|ий)$",   # сучка, сучара (но не «сучок», «сучковатый»)
    r"^муд(?:ак|ач|ил|озв|оеб)",         # мудак, мудила (но не «мудрый»)
    r"г[ао]ндон",
    r"^пид[оа]?р",                       # пидор, пидр, пидарас
    r"^педик(?:и|а|ов|у)?$",             # но не «педикюр»
    r"шлюх",
    r"шалав",
    r"залуп",
    r"^(?:по|на|за|от|у|об|вз|пере)?дроч",
    r"^чмо(?:шник|шный|шн)?$",           # но не «чмокнуть»
    r"^дерьм",
    r"^говн",
    r"^манд(?:а|ы|у|ой|авош|ить)$",      # но не «мандарин», «мандат»
    r"^(?:вы|за|об|на|по)?сра(?:ть|л|ла|ли|н|нь|ка|ч)",  # срать, насрал, срань (но не «сражение»)
    r"^жоп",
    r"^ублюд",
    r"^мраз",
    r"^уеб",
    r"^хер(?:ня|ни|ню|ней|ово|овый|овая|овое|овые|ового|овой|ачить|ачит|ас)$",  # но не «херувим»
    r"^пох(?:ер|уй)$",
    r"^даун(?:ы|ов|ам|ами|ах)?$",        # как оскорбление; «даунтаун», «даунгрейд» проходят
    r"^дебил(?:ы|а|у|ов|ам|ами|ах|ом|ка|ки|ку|ьный|ьная|ьное|ьные|ище)?$",   # не «дебилитирующий»
    r"^долбанн?(?:ый|ая|ое|ые|ого|ому|ой|ую|ым|ыми|ых|утый|утая|утое|утые|утого|утых)$",   # не «долбануть»
    r"^дибил(?:ы|а|у|ов|ам|ом)?$",
]

# Расистские, национальные оскорбления и экстремистские слова / символы.
_HATE = [
    r"^нигг(?:ер|еры|еров|ера|еру|ерам|ерами|ерах|ерша|а|ы)$",   # но не «Нигер», «Нигерия»
    r"^негр(?:ы|ов|у|ам|ами|ах|а|ила|илы|ил|итос|итосы|ит[оа]с)?$",
    r"^черномаз",
    r"черножоп",
    r"^чурк(?:а|и|ам|ами|ах|у|ой|обес)?$",
    r"^хач(?:и|ей|ам|ами|ах|у|а|ик|ики|ье|ьё)?$",   # но не «хачапури»
    r"^чучм[еа]к",
    r"^жид(?:ы|ов|ам|ами|ах|а|у|ом|яра|яры|овка|овки|омасон|омасоны|ос|осы)?$",  # но не «жидкий», «жидок»
    r"^жидовск",
    r"^узкоглаз",
    r"^хох(?:ол|лы|лов|лам|лами|лах|ла|лу|лом|лушка|лушки|лушку|лушкой|ляндия|ляндии|лятский|лятская|лятские|лятского)$",   # но не «хохолок», «хохлома»
    r"^кацап",
    r"^москал(?:ь|и|ей|ям|я|ю)$",        # но не фамилия «Москалёв»
    r"^пиндос",
    r"^русн(?:я|и|ю|ей)$",
    r"^свинорус",
    r"^укроп(?:ы|ов|ам|ами)$",           # во множ. числе — оскорбление; «укроп» (растение) проходит
    r"^чер?н[оа]мазый",
    r"^гитлер",
    r"^зиг(?:а|и|у|ой|уй|уйте|ую|ануть|анул|анула|анули|хайль)?$",   # но не «зигзаг»
    r"^хайл(?:ь|я)$",
    r"^зигхайл",
    r"^свастик",
    r"^ауе$",                            # запрещённое в РФ движение
    r"колумбайн",                        # признано террористическим в РФ
    r"^скулшут",
    r"^игил$",
    r"^нацик(?:и|ов)?$",
]
_WORD_RE = [re.compile(p) for p in _PROFANITY + _HATE]

# Проверяются по ИСХОДНОМУ тексту (латиница как есть, с границами слов)
_EN_RE = re.compile(
    r"\w*fuck\w*|\bf+u+c+k+\b|\bshit\w*|\w+shit\b|\bbitch\w*|\bcunt\w*|\basshole\w*|\bdickhead\w*"
    r"|\bpuss(?:y|ies)\b|\bwhores?\b|\bslut\w*|\bbastards?\b|\bcocksucker\w*|\bmotherf\w*"
    # расистские / экстремистские
    r"|\bnigg(?:a|as|az|ah|er|ers)\b|\bniga\b|\bkikes?\b|\bchinks?\b|\bspics?\b|\bgooks?\b|\bwetbacks?\b"
    r"|\bfag(?:s|got|gots)?\b|\bretard(?:s|ed)?\b|\btrann(?:y|ies)\b|\brahowa\b"
    r"|\bsieg\s*heil\b|\bheil\s+hitler\b|\bwhite\s+power\b|\bhitler\w*"
)
# Числовые и графические символы неонацистов
_SYMBOLS_RE = re.compile(r"(?<!\d)14[/|]?88(?![\d])|卐|卍|ϟϟ|ᛋᛋ|࿕|࿖")


@lru_cache(maxsize=1)
def _extra_words() -> frozenset[str]:
    """Точные слова из data/banwords.txt (по одному в строке, # — комментарий)."""
    if not EXTRA_WORDS_PATH.exists():
        return frozenset()
    words = set()
    for line in EXTRA_WORDS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            words.update(normalize_text(line))
    return frozenset(words)


def _is_banned_word(word: str) -> bool:
    if word in _extra_words():
        return True
    return any(r.search(word) for r in _WORD_RE)


def find_banned(text: str) -> list[str]:
    """Найденные запрещённые слова (в нормализованном виде). Пусто — текст чистый."""
    found = [w for w in normalize_text(text) if _is_banned_word(w)]
    lowered = (text or "").lower()
    found += _EN_RE.findall(lowered)
    found += _SYMBOLS_RE.findall(lowered)
    return found


def is_clean(text: str) -> bool:
    """True — можно сохранять и показывать другим; False — попросить переписать."""
    return not find_banned(text)


# ── Реклама и ссылки ─────────────────────────────────────────────────────────

# Доменные зоны, по которым узнаём ссылку без http:// (site.ru, t.me, vk.com …)
_TLDS = (
    "com|net|org|ru|su|рф|рус|москва|дети|io|me|co|ai|app|dev|info|biz|xyz|online|site|"
    "store|shop|pro|tech|tv|cc|ly|gg|to|ws|us|uk|de|ua|by|kz|uz|am|ge|link|live|club|"
    "top|space|fun|one|ink|bio|page|gd|so|vc|cx|im|pw|tk|win|bet|"
    "casino|games|money|click|website|world|today|cloud|host|eu|fm|lol|vip|red|cam"
)
# Технологии с «доменом» в названии — это не реклама
_TECH_NAMES = re.compile(
    r"\b(?:asp|ado|vb|ml|dot|entity)\.net\b|\bsocket\.io\b|\bnext\.js\b|\bbabylon\.js\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(
    rf"(?:https?|ftp|tg)\s*:\s*/+"                               # http://, tg://
    rf"|\bwww\s*\."                                              # www.
    rf"|[\w-]+\.(?:{_TLDS})\b"                                    # site.ru, t.me
    rf"|[\w-]+\s+\.\s*(?:{_TLDS})\b"                              # site .ru, site . ru
    rf"|[\w-]+\s*[(\[]?\s*(?:точка|тчк|dot)\s*[)\]]?\s*(?:{_TLDS}|ру|ком|нет|орг|ми)\b",  # site точка ru
    re.IGNORECASE,
)
# Упоминание канала/аккаунта: @channel (e-mail вида a@b.ru ловится как ссылка выше)
_MENTION_RE = re.compile(r"(?<![\w.])@[a-zA-Z0-9_]{3,}")


def has_link(text: str) -> bool:
    """Есть ли в тексте ссылка / домен (в т.ч. замаскированный «site точка ru»)."""
    cleaned = _TECH_NAMES.sub(" ", text or "")
    return bool(_URL_RE.search(cleaned))


def has_ads(text: str) -> bool:
    """Ссылка или @упоминание — для полей, где контактам и рекламе не место."""
    return has_link(text) or bool(_MENTION_RE.search(text or ""))


# ── GitHub ───────────────────────────────────────────────────────────────────

_GITHUB_RE = re.compile(
    r"^(?:(?:https?://)?(?:www\.)?github\.com/)?@?"
    r"(?P<user>[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9])){0,38})"
    r"(?:/(?P<repo>[\w.-]{1,100}))?/?$",
    re.IGNORECASE,
)


def normalize_github(text: str) -> str | None:
    """Ник или ссылка на GitHub → https://github.com/<ник>[/<репо>]. None — это не GitHub.

    Принимает: «user001», «@user001», «github.com/user001», «https://github.com/user001/repo».
    """
    match = _GITHUB_RE.match((text or "").strip())
    if not match:
        return None
    url = f"https://github.com/{match['user']}"
    if match["repo"]:
        url += f"/{match['repo']}"
    return url


# ── Контакт ──────────────────────────────────────────────────────────────────

_CONTACT_RE = re.compile(
    r"^(?:@[a-zA-Z0-9_.]{3,64}"                          # @ник
    r"|\+?[\d\s()\-]{7,20}"                              # телефон
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"                     # e-mail
    r"|[a-zA-Z0-9_.]{3,64})$"                            # ник без @
)


_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$")


def is_valid_contact(text: str) -> bool:
    """Контакт: @ник (MAX/Telegram), ник без @, телефон или e-mail. Ссылки нельзя."""
    value = (text or "").strip()
    if _EMAIL_RE.match(value):
        return True
    return bool(_CONTACT_RE.match(value)) and not has_link(value)

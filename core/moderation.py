import re
from functools import lru_cache
from pathlib import Path

EXTRA_WORDS_PATH = Path(__file__).resolve().parent.parent / "data" / "banwords.txt"


# Латиница и цифры, ПОХОЖИЕ на кириллицу внешне: xyй, 3аебал, п1зда
_VISUAL = str.maketrans({
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к", "m": "м", "o": "о",
    "p": "р", "t": "т", "x": "х", "y": "у", "u": "и", "r": "г", "n": "п",
    "0": "о", "3": "з", "4": "ч", "6": "б", "1": "и", "!": "и", "@": "а", "$": "с",
})

# Латиница ПО ЗВУЧАНИЮ
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

# Английские слова, которые в транслите случайно похожи на мат
_LATIN_SAFE = {
    "ebook", "ebooks", "ebay", "ebpf", "ebitda", "ebola", "hue", "hues", "huey", "hui",
    "huawei", "hyundai", "sukhoi", "mudra", "bleach", "xue", "suki", "gown", "gowns",
    "ebony", "eben", "ebb", "ebbs", "ebbing", "ebba", "ebert", "ebenezer", "zig", "hachi", "negra", "niger",
    "aye", "manda", "huerta", "huygens", "huevos", "huer", "zigzag",
}

# Символы, которыми маскируют мат внутри слова
_MASK_CHARS = re.compile(r"[*_\-.,'`~^#%&+=|\"«»]+")

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
        chunk = chunk.strip("!")
        pieces = {_MASK_CHARS.sub("", chunk)} | set(_MASK_CHARS.split(chunk))
        for piece in pieces:
            if not piece:
                continue
            if piece in _LATIN_SAFE:
                continue
            variants = []
            visual = piece.translate(_VISUAL)
            if not re.search(r"[a-z]", visual):
                variants.append(visual)
            variants.append(_translit(piece))
            for variant in variants:
                for word in re.findall(r"[а-я]+", variant):
                    words.append(word)
                    words.append(_squash_repeats(word))
    return list(dict.fromkeys(words))


#Запрещённые слова

_PREFIX = r"(?:по|на|ни|за|от|до|вы|у|о|об|раз|рас|с|съ|под|при|пере|недо|про|вз|вс|из|ис)?"
_PREFIX_EB = r"(?:по|на|ни|за|от|до|вы|у|о|раз|рас|под|при|пере|недо|про|долбо|вз|из)?"
_PROFANITY = [
    rf"^{_PREFIX}ху[йеяюи]",            
    r"(?<!стра)(?<!штри)(?<!пси)(?<!пло)ху(?:й|е[вс])", 
    r"долбо[её]б",
    r"пизд", 
    r"^пизж",  
    rf"^{_PREFIX_EB}еб(?:а|у|л|н|ш|и|е|о|с|к|ц|ыв)", 
    rf"^{_PREFIX}ъеб",
    r"бляд",
    r"^бля(?:т|ть|ха-муха)?$",
    r"^сук(?:а|и|у|ой|ам|ами|ах|ин|ина|ины|ину|ины)$",
    r"^суч(?:ка|ки|ке|ку|кой|ками|ках|ара|ары|аре|ий)$",
    r"^муд(?:ак|ач|ил|озв|оеб)",
    r"г[ао]ндон",
    r"^пид[оа]?р",
    r"^педик(?:и|а|ов|у)?$",
    r"шлюх",
    r"шалав",
    r"залуп",
    r"^(?:по|на|за|от|у|об|вз|пере)?дроч",
    r"^чмо(?:шник|шный|шн)?$",
    r"^дерьм",
    r"^говн",
    r"^манд(?:а|ы|у|ой|авош|ить)$",
    r"^(?:вы|за|об|на|по)?сра(?:ть|л|ла|ли|н|нь|ка|ч)",
    r"^жоп",
    r"^ублюд",
    r"^мраз",
    r"^уеб",
    r"^хер(?:ня|ни|ню|ней|ово|овый|овая|овое|овые|ового|овой|ачить|ачит|ас)$",
    r"^пох(?:ер|уй)$",
    r"^даун(?:ы|ов|ам|ами|ах)?$",
    r"^дебил(?:ы|а|у|ов|ам|ами|ах|ом|ка|ки|ку|ьный|ьная|ьное|ьные|ище)?$",
    r"^долбанн?(?:ый|ая|ое|ые|ого|ому|ой|ую|ым|ыми|ых|утый|утая|утое|утые|утого|утых)$",
    r"^дибил(?:ы|а|у|ов|ам|ом)?$",
]

# Расистские, национальные оскорбления и экстремистские слова
_HATE = [
    r"^нигг(?:ер|еры|еров|ера|еру|ерам|ерами|ерах|ерша|а|ы)$",
    r"^негр(?:ы|ов|у|ам|ами|ах|а|ила|илы|ил|итос|итосы|ит[оа]с)?$",
    r"^черномаз",
    r"черножоп",
    r"^чурк(?:а|и|ам|ами|ах|у|ой|обес)?$",
    r"^хач(?:и|ей|ам|ами|ах|у|а|ик|ики|ье|ьё)?$",
    r"^чучм[еа]к",
    r"^жид(?:ы|ов|ам|ами|ах|а|у|ом|яра|яры|овка|овки|омасон|омасоны|ос|осы)?$",
    r"^жидовск",
    r"^узкоглаз",
    r"^хох(?:ол|лы|лов|лам|лами|лах|ла|лу|лом|лушка|лушки|лушку|лушкой|ляндия|ляндии|лятский|лятская|лятские|лятского)$", 
    r"^кацап",
    r"^москал(?:ь|и|ей|ям|я|ю)$",
    r"^пиндос",
    r"^русн(?:я|и|ю|ей)$",
    r"^свинорус",
    r"^укроп(?:ы|ов|ам|ами)$", 
    r"^чер?н[оа]мазый",
    r"^гитлер",
    r"^зиг(?:а|и|у|ой|уй|уйте|ую|ануть|анул|анула|анули|хайль)?$",   # но не «зигзаг»
    r"^хайл(?:ь|я)$",
    r"^зигхайл",
    r"^свастик",
    r"^ауе$", 
    r"колумбайн", 
    r"^скулшут",
    r"^игил$",
    r"^нацик(?:и|ов)?$",
]
_WORD_RE = [re.compile(p) for p in _PROFANITY + _HATE]

_EN_RE = re.compile(
    r"\w*fuck\w*|\bf+u+c+k+\b|\bshit\w*|\w+shit\b|\bbitch\w*|\bcunt\w*|\basshole\w*|\bdickhead\w*"
    r"|\bpuss(?:y|ies)\b|\bwhores?\b|\bslut\w*|\bbastards?\b|\bcocksucker\w*|\bmotherf\w*"
    r"|\bnigg(?:a|as|az|ah|er|ers)\b|\bniga\b|\bkikes?\b|\bchinks?\b|\bspics?\b|\bgooks?\b|\bwetbacks?\b"
    r"|\bfag(?:s|got|gots)?\b|\bretard(?:s|ed)?\b|\btrann(?:y|ies)\b|\brahowa\b"
    r"|\bsieg\s*heil\b|\bheil\s+hitler\b|\bwhite\s+power\b|\bhitler\w*"
)

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


_TLDS = (
    "com|net|org|ru|su|рф|рус|москва|дети|io|me|co|ai|app|dev|info|biz|xyz|online|site|"
    "store|shop|pro|tech|tv|cc|ly|gg|to|ws|us|uk|de|ua|by|kz|uz|am|ge|link|live|club|"
    "top|space|fun|one|ink|bio|page|gd|so|vc|cx|im|pw|tk|win|bet|"
    "casino|games|money|click|website|world|today|cloud|host|eu|fm|lol|vip|red|cam"
)

_TECH_NAMES = re.compile(
    r"\b(?:asp|ado|vb|ml|dot|entity)\.net\b|\bsocket\.io\b|\bnext\.js\b|\bbabylon\.js\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(
    rf"(?:https?|ftp|tg)\s*:\s*/+"                 
    rf"|\bwww\s*\."                                      
    rf"|[\w-]+\.(?:{_TLDS})\b"                               
    rf"|[\w-]+\s+\.\s*(?:{_TLDS})\b"                        
    rf"|[\w-]+\s*[(\[]?\s*(?:точка|тчк|dot)\s*[)\]]?\s*(?:{_TLDS}|ру|ком|нет|орг|ми)\b", 
    re.IGNORECASE,
)

_EMAIL_ANY_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def has_link(text: str) -> bool:
    """Есть ли в тексте ссылка на сайт / домен (в т.ч. замаскированный «site точка ru»).

    E-mail и @ники ссылками не считаются.
    """
    cleaned = _EMAIL_ANY_RE.sub(" ", text or "")
    cleaned = _TECH_NAMES.sub(" ", cleaned)
    return bool(_URL_RE.search(cleaned))


def has_ads(text: str) -> bool:
    """Реклама = ссылка или домен. @ники (@username) рекламой не считаем — это контакты VK/TG."""
    return has_link(text)



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


# Контакт


def is_valid_contact(text: str) -> bool:
    """Контакт — любой текст без ссылок на сайты: @ник, «ТГ: @ivan, VK: @ivan», телефон, e-mail."""
    return not has_link(text)

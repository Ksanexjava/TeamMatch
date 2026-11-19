import os
from dataclasses import dataclass
from pathlib import Path

def _load_dotenv() -> None:
    """Читает .env из корня проекта, если он есть (для запуска без Docker).

    Уже заданные переменные окружения не перезаписываются.
    """
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

_load_dotenv()

@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    redis_url: str
    log_level: str
    seed_test_profiles: bool
    telegram_bot_token: str
    telegram_api_base: str
    webapp_url: str
    media_dir: str
    init_data_ttl: int
    dev_auth: bool
    telegram_bot_username: str
    max_bot_username: str
    consent_version: str
    support_email: str
    admin_token: str
    telegram_webapp_button: bool

    @property
    def legal_base_url(self) -> str:
        """Где опубликованы согласие и политика: LEGAL_BASE_URL или адрес мини-приложения."""
        return (os.environ.get("LEGAL_BASE_URL") or self.webapp_url).rstrip("/")

    @property
    def consent_url(self) -> str:
        return f"{self.legal_base_url}/legal/consent" if self.legal_base_url else ""

    @property
    def privacy_url(self) -> str:
        return f"{self.legal_base_url}/legal/privacy" if self.legal_base_url else ""


# Федеральный закон от 27.07.2006 № 152-ФЗ «О персональных данных» — актуальная редакция.
LAW_152_URL = "https://www.consultant.ru/document/cons_doc_LAW_61801/"

settings = Settings(
    bot_token=os.environ.get("MAX_BOT_TOKEN", ""),
    database_url=os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///./local.db",
    redis_url=os.environ.get("REDIS_URL", ""),
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    seed_test_profiles=os.environ.get("SEED_TEST_PROFILES", "1") == "1",
    # Мини-приложение и Telegram
    telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    # Свой ретранслятор Bot API. Пусто — ходим в api.telegram.org напрямую.
    # Нужен там, где хостинг не выпускает соединения к Telegram (см. DEPLOY.md).
    telegram_api_base=os.environ.get("TELEGRAM_API_BASE", "").strip().rstrip("/"),
    webapp_url=os.environ.get("WEBAPP_URL", "").rstrip("/"),
    media_dir=os.environ.get("MEDIA_DIR", "./media"),
    init_data_ttl=int(os.environ.get("INIT_DATA_TTL", "86400")),
    # Только для локальной разработки: пускает без подписи мессенджера. На сервере — 0.
    dev_auth=os.environ.get("WEBAPP_DEV_AUTH", "0") == "1",
    # Имена ботов без @ — для ссылок «подключить второй мессенджер»
    telegram_bot_username=os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@"),
    max_bot_username=os.environ.get("MAX_BOT_USERNAME", "").lstrip("@"),
    # Редакция согласия на обработку ПД. Меняется вместе с текстом webapp/static/legal/consent.html.
    consent_version=os.environ.get("CONSENT_VERSION", "2026-11-17"),
    support_email=os.environ.get("SUPPORT_EMAIL", "m.mikhailov2@g.nsu.ru"),
    # Пусто — редактор мероприятий выключен целиком. Так он не окажется
    # открытым по недосмотру: включается только явно заданным токеном.
    admin_token=os.environ.get("ADMIN_TOKEN", "").strip(),
    # 0 — Telegram-бот не показывает кнопку мини-приложения (например, пока оно
    # недоступно части пользователей) и работает только кнопками в чате.
    telegram_webapp_button=os.environ.get("TELEGRAM_WEBAPP_BUTTON", "1") != "0",
)

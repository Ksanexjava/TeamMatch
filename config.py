# config.py
# Все настройки берутся из переменных окружения (файл .env или docker compose).
# Токен НИКОГДА не пишем в код — только в .env, который не попадает в Git.

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


settings = Settings(
    bot_token=os.environ.get("MAX_BOT_TOKEN", ""),
    # По умолчанию — локальный файл SQLite: можно запустить бота без Docker и Postgres
    database_url=os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///./local.db",
    # Пусто → состояния анкеты хранятся в памяти (при перезапуске бота сбрасываются)
    redis_url=os.environ.get("REDIS_URL", ""),
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    seed_test_profiles=os.environ.get("SEED_TEST_PROFILES", "1") == "1",
)

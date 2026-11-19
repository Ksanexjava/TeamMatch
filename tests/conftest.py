import os
import tempfile
from pathlib import Path

# Настройки читаются при импорте config, поэтому окружение задаём до любых импортов проекта.
_tmp = Path(tempfile.mkdtemp(prefix="teammatch-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["MEDIA_DIR"] = str(_tmp / "media")
os.environ["WEBAPP_DEV_AUTH"] = "1"
os.environ["SEED_TEST_PROFILES"] = "1"
os.environ["MAX_BOT_TOKEN"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["REDIS_URL"] = ""
# Локальный .env не должен влиять на тесты (config подхватывает его только для незаданных переменных).
for _name in ("TELEGRAM_BOT_USERNAME", "MAX_BOT_USERNAME", "WEBAPP_URL", "WEBAPP_DOMAIN", "LEGAL_BASE_URL", "ADMIN_TOKEN"):
    os.environ[_name] = ""
os.environ["TELEGRAM_WEBAPP_BUTTON"] = "1"

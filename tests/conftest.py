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

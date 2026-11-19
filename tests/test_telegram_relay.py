"""Ретранслятор Bot API: подменяет адрес Telegram, не трогая остальной код.

Сети здесь нет — проверяем ровно то, куда пойдут запросы.
"""

from dataclasses import replace

import pytest

from config import settings
from messengers import telegram as tg
from tgbot.main import build_bot

TOKEN = "123456789:AAHfake-token-for-tests-only-00000000000"
RELAY = "https://teammate-tg.example.workers.dev/s3cret"


def with_settings(monkeypatch, **kwargs):
    """Подменяет настройки там, где модули их уже импортировали по имени."""
    patched = replace(settings, telegram_bot_token=TOKEN, **kwargs)
    monkeypatch.setattr(tg, "settings", patched)
    monkeypatch.setattr("tgbot.main.settings", patched)
    return patched


def test_уведомления_идут_в_telegram_без_ретранслятора(monkeypatch):
    with_settings(monkeypatch, telegram_api_base="")
    assert tg.api_url("sendMessage") == f"https://api.telegram.org/bot{TOKEN}/sendMessage"


def test_уведомления_идут_через_ретранслятор(monkeypatch):
    with_settings(monkeypatch, telegram_api_base=RELAY)
    assert tg.api_url("sendMessage") == f"{RELAY}/bot{TOKEN}/sendMessage"


@pytest.mark.parametrize("base", ["", RELAY])
def test_бот_берёт_адрес_из_настроек(monkeypatch, base):
    with_settings(monkeypatch, telegram_api_base=base)
    bot = build_bot()
    expected = base or "https://api.telegram.org"
    assert bot.session.api.base.startswith(expected)
    # Путь к методам строится по правилам Bot API независимо от хоста.
    assert bot.session.api.api_url(token=TOKEN, method="getMe") == f"{expected}/bot{TOKEN}/getMe"

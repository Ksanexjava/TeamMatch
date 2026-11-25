"""Отдельный адрес мини-приложения для Telegram.

Прямой домен доступен не всем: из-под VPN до российского IP трафик не
доходит. Для Telegram перед приложением можно поставить ретранслятор, и
тогда кнопки в этом мессенджере должны вести на него, а не на домен.
MAX при этом остаётся на прямом адресе.
"""

from dataclasses import replace

from config import settings
from messengers import telegram as tg

DIRECT = "https://teammatensu.ru"
PROXY = "https://teammate-app.example.workers.dev"


def test_без_переменной_берётся_общий_адрес():
    s = replace(settings, webapp_url=DIRECT, telegram_webapp_url_raw="")
    assert s.telegram_webapp_url == DIRECT


def test_с_переменной_телеграм_уходит_на_ретранслятор():
    s = replace(settings, webapp_url=DIRECT, telegram_webapp_url_raw=PROXY)
    assert s.telegram_webapp_url == PROXY
    # Общий адрес не меняется: MAX и ссылки на документы остаются прямыми.
    assert s.webapp_url == DIRECT
    assert s.legal_base_url == DIRECT


def test_кнопка_под_уведомлением_ведёт_на_ретранслятор(monkeypatch):
    monkeypatch.setattr(
        tg, "settings",
        replace(settings, webapp_url=DIRECT, telegram_webapp_url_raw=PROXY,
                telegram_webapp_button=True),
    )
    markup = tg.open_app_markup()
    assert markup["inline_keyboard"][0][0]["web_app"]["url"] == PROXY + "/"


def test_без_адреса_кнопки_мини_приложения_нет(monkeypatch):
    monkeypatch.setattr(
        tg, "settings",
        replace(settings, webapp_url="", telegram_webapp_url_raw="", telegram_webapp_button=True),
    )
    assert tg.open_app_markup() is None

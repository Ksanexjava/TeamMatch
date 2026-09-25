# bot/handlers — обработчики событий бота, разбиты по зонам ответственности.
# Порядок важен: fallback всегда последний.

from bot.handlers import fallback, feed, profile, start

routers = [start.router, profile.router, feed.router, fallback.router]

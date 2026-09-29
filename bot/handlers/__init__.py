from bot.handlers import fallback, feed, profile, start

routers = [start.router, profile.router, feed.router, fallback.router]

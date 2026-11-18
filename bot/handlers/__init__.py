from bot.handlers import fallback, feed, link, profile, start

routers = [link.router, start.router, profile.router, feed.router, fallback.router]

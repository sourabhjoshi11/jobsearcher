"""Builds and returns the PTB Application singleton.

webhook_mode=True  -> Updater disabled; updates arrive via POST /webhook/telegram.
webhook_mode=False -> Updater enabled; bot polls the Telegram API (local dev).
"""

from __future__ import annotations

from loguru import logger
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from app.bot.handlers.commands import help_cmd, start
from app.bot.handlers.subscribe import subscribe
from app.bot.handlers.onboarding import (
    pause,
    profile,
    resume,
    setcity,
    setexperience,
    setskills,
)
from app.config import get_settings

_application: Application | None = None


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(
        "Unhandled Telegram error | update={} error={}",
        update, context.error, exc_info=context.error,
    )


def build_application(*, webhook_mode: bool) -> Application:
    global _application
    settings = get_settings()
    builder = ApplicationBuilder().token(settings.telegram_bot_token)
    if webhook_mode:
        builder = builder.updater(None)

    app = builder.build()

    # Core
    app.add_handler(CommandHandler("start",         start))
    app.add_handler(CommandHandler("help",          help_cmd))
    # Onboarding
    app.add_handler(CommandHandler("setskills",     setskills))
    app.add_handler(CommandHandler("setcity",       setcity))
    app.add_handler(CommandHandler("setexperience", setexperience))
    app.add_handler(CommandHandler("pause",         pause))
    app.add_handler(CommandHandler("resume",        resume))
    app.add_handler(CommandHandler("profile",       profile))
    app.add_handler(CommandHandler("subscribe",     subscribe))

    app.add_error_handler(_error_handler)
    _application = app
    return app


def get_application() -> Application:
    """Return the running Application singleton (set by build_application)."""
    if _application is None:
        raise RuntimeError("Bot application not initialised — call build_application() first.")
    return _application

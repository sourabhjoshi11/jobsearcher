"""FastAPI application entrypoint.

Lifecycle
---------
1. Postgres pool + Redis client are opened.
2. Telegram bot is initialised.
   - webhook_url set  -> webhook mode  (production / staging)
   - webhook_url empty -> polling mode (local dev, no public URL needed)
3. Scraper scheduler starts.
4. FastAPI serves requests.
5. On shutdown everything is torn down in reverse order.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.routes.webhook import router as webhook_router
from app.api.routes.payments import router as payments_router
from app.bot.application import build_application
from app.config import get_settings
from app.db import connection as db
from app.db import redis as cache
from app.logging_setup import configure_logging
from app.scraper.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    logger.info(
        "Starting Job Alert Bot API | env={} log_level={}",
        settings.environment,
        settings.log_level,
    )

    await db.init_pool()
    await cache.init_redis()

    # --- Telegram bot ---------------------------------------------------
    # no token        -> bot disabled (fine for pure-API deployments)
    # token, no URL   -> polling mode (local dev)
    # token + URL     -> webhook mode (staging / prod)
    bot_app = None
    polling_started = False

    if settings.telegram_bot_token:
        use_webhook = bool(settings.webhook_url)
        bot_app = build_application(webhook_mode=use_webhook)
        await bot_app.initialize()
        await bot_app.start()
        app.state.bot_application = bot_app

        if use_webhook:
            webhook_url = f"{settings.webhook_url}/webhook/telegram"
            await bot_app.bot.set_webhook(webhook_url)
            logger.info("Telegram webhook registered: {}", webhook_url)
        else:
            await bot_app.updater.start_polling(drop_pending_updates=True)
            polling_started = True
            logger.info("Telegram bot started in polling mode")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not set -- bot disabled")

    # --- Scraper scheduler ----------------------------------------------
    start_scheduler()

    try:
        yield
    finally:
        stop_scheduler()

        if bot_app is not None:
            if polling_started:
                await bot_app.updater.stop()
            elif settings.webhook_url:
                await bot_app.bot.delete_webhook()
            await bot_app.stop()
            await bot_app.shutdown()

        await cache.close_redis()
        await db.close_pool()
        logger.info("Shutdown complete")


app = FastAPI(
    title="Job Alert Bot",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhook_router)
app.include_router(payments_router)


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness + dependency check.

    Returns 200 when Postgres and Redis are reachable, 503 otherwise.
    """
    db_ok = await db.ping()
    redis_ok = await cache.ping()
    body = {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "db": "ok" if db_ok else "down",
        "redis": "ok" if redis_ok else "down",
    }
    return JSONResponse(content=body, status_code=200 if (db_ok and redis_ok) else 503)


@app.get("/")
async def root() -> dict:
    return {"service": "job-alert-bot", "version": "0.1.0"}

"""Telegram webhook endpoint.

Route:  POST /webhook/telegram
Auth:   Telegram sends the request; no token in URL (security-by-obscurity is
        sufficient here because the URL is only known to Telegram).  If you
        want an extra layer, add a secret_token via bot.set_webhook() and
        validate the X-Telegram-Bot-Api-Secret-Token header.

The PTB Application is stored on FastAPI's app.state so we don't need a global
or DI container.  We return HTTP 200 immediately after queuing the update —
Telegram retries on non-2xx responses, so fast acks matter.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from loguru import logger
from telegram import Update

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/telegram")
async def telegram_webhook(request: Request) -> Response:
    bot_app = getattr(request.app.state, "bot_application", None)
    if bot_app is None:
        logger.error("Telegram bot application not found on app.state")
        return Response(status_code=503)

    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return Response(status_code=200)

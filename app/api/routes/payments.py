"""Razorpay webhook + callback endpoints.

POST /webhook/razorpay
    Receives payment events from Razorpay (payment_link.paid).
    Verifies HMAC-SHA256 signature, upgrades user to premium,
    and sends a Telegram confirmation.

GET /webhook/razorpay/callback
    Browser redirect after payment — just shows a thank-you message.
    Real confirmation comes from the webhook above.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from loguru import logger

from app.config import get_settings
from app.db import connection as db
from app.db.payments import capture_payment, get_user_id_by_order

router = APIRouter(prefix="/webhook", tags=["webhook"])

_THANK_YOU_HTML = """
<!doctype html><html><head><meta charset="utf-8">
<title>Payment Successful</title></head>
<body style="font-family:sans-serif;text-align:center;padding:3rem">
<h2>Payment successful!</h2>
<p>You are now a <strong>Premium</strong> member.<br>
Go back to Telegram to start receiving alerts.</p>
</body></html>
"""


@router.post("/razorpay")
async def razorpay_webhook(request: Request) -> Response:
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    settings = get_settings()

    if not _verify_signature(body, signature, settings.razorpay_webhook_secret):
        logger.warning("Razorpay webhook: invalid signature")
        return Response(status_code=400)

    event_data = json.loads(body)
    event = event_data.get("event", "")

    if event == "payment_link.paid":
        await _handle_payment_paid(request, event_data)

    return Response(status_code=200)


@router.get("/razorpay/callback")
async def razorpay_callback() -> HTMLResponse:
    return HTMLResponse(_THANK_YOU_HTML)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _handle_payment_paid(request: Request, data: dict) -> None:
    try:
        payload    = data["payload"]["payment_link"]["entity"]
        order_id   = payload.get("order_id", "")
        payment_id = data["payload"]["payment"]["entity"]["id"]
        signature  = data["payload"]["payment"]["entity"].get("signature", "")

        async with db.get_pool().acquire() as conn:
            async with conn.transaction():
                payment = await capture_payment(
                    conn,
                    razorpay_order_id=order_id,
                    razorpay_payment_id=payment_id,
                    razorpay_signature=signature,
                )
                if not payment:
                    logger.warning("Razorpay webhook: order not found | order_id={}", order_id)
                    return

                user_row = await conn.fetchrow(
                    "SELECT telegram_id FROM users WHERE user_id = $1",
                    payment["user_id"],
                )

        if user_row:
            await _notify_user(request, user_row["telegram_id"])

        logger.info(
            "Payment captured | order_id={} payment_id={} user_id={}",
            order_id, payment_id, payment["user_id"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Razorpay webhook processing error: {}", exc, exc_info=exc)


async def _notify_user(request: Request, telegram_id: int) -> None:
    bot_app = getattr(request.app.state, "bot_application", None)
    if not bot_app:
        return
    try:
        await bot_app.bot.send_message(
            chat_id=telegram_id,
            text=(
                "<b>You're now Premium!</b>\n\n"
                "You'll receive up to 10 job alerts per cycle with salary filters. "
                "Use /profile to confirm your plan."
            ),
            parse_mode="HTML",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not notify user after payment | telegram_id={} error={}", telegram_id, exc)

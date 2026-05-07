"""Payment handler — /subscribe command.

Flow
----
1. User sends /subscribe.
2. Bot creates a Razorpay Payment Link (Rs. 99/month).
3. Bot sends the link; user pays in browser.
4. Razorpay POSTs to /webhook/razorpay on success.
5. Webhook upgrades user to premium and sends confirmation.

The razorpay SDK is synchronous, so we run it in a thread-pool executor.
"""

from __future__ import annotations

import asyncio
from functools import partial

import razorpay
from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from app.config import get_settings
from app.db import connection as db
from app.db.payments import create_payment_record

_AMOUNT_PAISE = 9900          # Rs. 99
_CURRENCY     = "INR"
_PLAN_LABEL   = "Job Alert Bot — Premium (1 Month)"


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    settings = get_settings()
    if not settings.razorpay_key_id:
        await update.message.reply_text(
            "Payments are not enabled yet. Check back soon!"
        )
        return

    tg_id = update.effective_user.id
    first_name = update.effective_user.first_name or "User"

    # Create Razorpay payment link in executor (SDK is sync)
    loop = asyncio.get_event_loop()
    try:
        link_data = await loop.run_in_executor(
            None,
            partial(_create_payment_link, settings, first_name),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Razorpay link creation failed | telegram_id={} error={}", tg_id, exc)
        await update.message.reply_text(
            "Could not create payment link. Please try again later."
        )
        return

    # Persist pending payment so webhook can look it up
    async with db.get_pool().acquire() as conn:
        # get user_id from telegram_id
        row = await conn.fetchrow(
            "SELECT user_id FROM users WHERE telegram_id = $1", tg_id
        )
        if not row:
            await update.message.reply_text("Please send /start first.")
            return
        await create_payment_record(
            conn,
            user_id=row["user_id"],
            amount_paise=_AMOUNT_PAISE,
            razorpay_order_id=link_data["order_id"],
        )

    logger.info("Payment link created | telegram_id={} order_id={}", tg_id, link_data["order_id"])
    await update.message.reply_html(
        f"<b>Upgrade to Premium — Rs. 99/month</b>\n\n"
        f"Get unlimited job alerts + salary filters.\n\n"
        f'<a href="{link_data["short_url"]}">Pay Now →</a>'
    )


def _create_payment_link(settings, customer_name: str) -> dict:
    """Synchronous Razorpay call — run via executor."""
    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    return client.payment_link.create({
        "amount":       _AMOUNT_PAISE,
        "currency":     _CURRENCY,
        "description":  _PLAN_LABEL,
        "customer":     {"name": customer_name},
        "notify":       {"sms": False, "email": False},
        "callback_url": f"{settings.webhook_url}/webhook/razorpay/callback",
        "callback_method": "get",
    })

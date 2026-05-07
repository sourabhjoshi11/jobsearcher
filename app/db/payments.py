"""Payments + subscriptions repository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg

_PREMIUM_DAYS = 30


async def create_payment_record(
    conn: asyncpg.Connection,
    *,
    user_id: int,
    amount_paise: int,
    razorpay_order_id: str,
) -> int:
    """Insert a pending payment row. Returns payment_id."""
    row = await conn.fetchrow(
        """
        INSERT INTO payments (user_id, amount_paise, status, razorpay_order_id)
        VALUES ($1, $2, 'created', $3)
        RETURNING payment_id
        """,
        user_id,
        amount_paise,
        razorpay_order_id,
    )
    return row["payment_id"]


async def capture_payment(
    conn: asyncpg.Connection,
    *,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> asyncpg.Record | None:
    """Mark payment captured; upgrade user to premium; create subscription.

    Returns the updated payments row, or None if order not found.
    All three writes happen in the caller's transaction.
    """
    payment = await conn.fetchrow(
        """
        UPDATE payments
        SET status              = 'captured',
            razorpay_payment_id = $2,
            razorpay_signature  = $3,
            updated_at          = NOW()
        WHERE razorpay_order_id = $1
        RETURNING payment_id, user_id, amount_paise
        """,
        razorpay_order_id,
        razorpay_payment_id,
        razorpay_signature,
    )
    if not payment:
        return None

    user_id = payment["user_id"]
    now = datetime.now(tz=timezone.utc)
    end = now + timedelta(days=_PREMIUM_DAYS)

    await conn.execute(
        "UPDATE users SET plan = 'premium', updated_at = NOW() WHERE user_id = $1",
        user_id,
    )
    await conn.execute(
        """
        INSERT INTO subscriptions
            (user_id, plan, status, start_date, end_date, razorpay_order_id, razorpay_payment_id)
        VALUES ($1, 'premium_monthly', 'active', $2, $3, $4, $5)
        """,
        user_id,
        now,
        end,
        razorpay_order_id,
        razorpay_payment_id,
    )
    return payment


async def get_user_id_by_order(
    conn: asyncpg.Connection, razorpay_order_id: str
) -> int | None:
    row = await conn.fetchrow(
        "SELECT user_id FROM payments WHERE razorpay_order_id = $1",
        razorpay_order_id,
    )
    return row["user_id"] if row else None

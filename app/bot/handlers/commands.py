"""Core command handlers — /start and /help."""

from __future__ import annotations

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from app.db import connection as db
from app.db.users import upsert_user

_WELCOME = (
    "<b>👋 Welcome to Job Alert Bot!</b>\n\n"
    "I push curated job listings straight to you — no portal-hopping needed.\n\n"
    "<b>Quick setup (takes 30 seconds):</b>\n"
    "1. /setskills python,django\n"
    "2. /setcity bangalore,remote\n"
    "3. /setexperience 2_5\n\n"
    "Then sit back — alerts land automatically."
)

_HELP = (
    "<b>Commands</b>\n\n"
    "<b>Setup</b>\n"
    "/setskills &lt;skill1,skill2&gt;     — Set your skills\n"
    "/setcity &lt;city1,remote&gt;        — Set preferred cities\n"
    "/setexperience &lt;band&gt;          — Set experience band\n\n"
    "<b>Control</b>\n"
    "/pause   — Stop receiving alerts\n"
    "/resume  — Resume alerts\n"
    "/profile — View your current settings\n\n"
    "<b>Other</b>\n"
    "/subscribe — Upgrade to Premium (Rs. 99/mo)\n"
    "/help      — Show this message\n\n"
    "<i>Experience bands: fresher · 0_2 · 2_5 · 5_10 · 10_plus</i>"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    async with db.get_pool().acquire() as conn:
        user = await upsert_user(conn, update.effective_user)
    logger.info("User upserted | telegram_id={} plan={}", user["telegram_id"], user["plan"])
    await update.message.reply_html(_WELCOME)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_html(_HELP)

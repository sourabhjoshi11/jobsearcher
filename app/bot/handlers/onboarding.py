"""Onboarding command handlers.

/setskills python,django,react  -- update skill preferences
/setcity   bangalore,remote     -- update city + remote flag
/setexperience 2_5              -- update experience band
/pause                          -- stop receiving alerts
/resume                         -- resume alerts
/profile                        -- show current settings
"""

from __future__ import annotations

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from app.db import connection as db
from app.db.users import (
    get_user,
    set_paused,
    update_cities,
    update_experience,
    update_skills,
)

_EXP_LABELS: dict[str, str] = {
    "fresher": "Fresher (0 yrs)",
    "0_2":     "0-2 years",
    "2_5":     "2-5 years",
    "5_10":    "5-10 years",
    "10_plus": "10+ years",
}
_VALID_EXP = set(_EXP_LABELS)
_MAX_SKILLS = 20
_MAX_CITIES = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_list(args: list[str]) -> list[str]:
    """Accept both comma-separated and space-separated input."""
    raw = ",".join(args)
    return [s.strip().lower() for s in raw.split(",") if s.strip()]


async def _require_registered(update: Update) -> bool:
    """Send an error and return False if update has no message/user."""
    if not update.effective_user or not update.message:
        return False
    return True


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def setskills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_registered(update):
        return
    if not context.args:
        await update.message.reply_html(
            "Usage: <code>/setskills python,django,react</code>\n"
            "Separate skills with commas or spaces."
        )
        return

    skills = _parse_list(context.args)[:_MAX_SKILLS]
    if not skills:
        await update.message.reply_text("No valid skills found. Try: /setskills python,django")
        return

    async with db.get_pool().acquire() as conn:
        await update_skills(conn, update.effective_user.id, skills)

    logger.info("Skills updated | telegram_id={} skills={}", update.effective_user.id, skills)
    await update.message.reply_html(
        f"Skills saved: <b>{', '.join(skills)}</b>\n\n"
        "Next: set your city with /setcity"
    )


async def setcity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_registered(update):
        return
    if not context.args:
        await update.message.reply_html(
            "Usage: <code>/setcity bangalore,mumbai,remote</code>\n"
            "Add <b>remote</b> to also receive remote jobs."
        )
        return

    items = _parse_list(context.args)[:_MAX_CITIES]
    include_remote = "remote" in items
    cities = [c for c in items if c != "remote"]

    async with db.get_pool().acquire() as conn:
        await update_cities(conn, update.effective_user.id, cities, include_remote)

    remote_str = " + Remote" if include_remote else ""
    display = ", ".join(cities) + remote_str if cities else "Remote only"
    logger.info("Cities updated | telegram_id={} cities={} remote={}", update.effective_user.id, cities, include_remote)
    await update.message.reply_html(
        f"Cities saved: <b>{display}</b>\n\n"
        "Next: set your experience with /setexperience"
    )


async def setexperience(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_registered(update):
        return
    if not context.args or context.args[0].lower() not in _VALID_EXP:
        opts = "\n".join(f"  <code>{k}</code> — {v}" for k, v in _EXP_LABELS.items())
        await update.message.reply_html(
            f"Usage: <code>/setexperience &lt;option&gt;</code>\n\nOptions:\n{opts}"
        )
        return

    exp = context.args[0].lower()
    async with db.get_pool().acquire() as conn:
        await update_experience(conn, update.effective_user.id, exp)

    logger.info("Experience updated | telegram_id={} exp={}", update.effective_user.id, exp)
    await update.message.reply_html(
        f"Experience set to: <b>{_EXP_LABELS[exp]}</b>\n\n"
        "You're all set! Use /profile to review your settings."
    )


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_registered(update):
        return
    async with db.get_pool().acquire() as conn:
        await set_paused(conn, update.effective_user.id, True)
    await update.message.reply_html(
        "Alerts <b>paused</b>. Use /resume to turn them back on."
    )


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_registered(update):
        return
    async with db.get_pool().acquire() as conn:
        await set_paused(conn, update.effective_user.id, False)
    await update.message.reply_html(
        "Alerts <b>resumed</b>! You'll receive new matches shortly."
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_registered(update):
        return
    async with db.get_pool().acquire() as conn:
        user = await get_user(conn, update.effective_user.id)

    if not user:
        await update.message.reply_text("You're not registered yet. Send /start first.")
        return

    skills = ", ".join(user["skills"]) or "<i>not set</i>"
    cities = ", ".join(user["cities"]) or ""
    remote = " + Remote" if user["include_remote"] else ""
    location = (cities + remote) or "<i>not set</i>"
    exp = _EXP_LABELS.get(user["experience"], user["experience"])
    plan = "Premium" if user["plan"] == "premium" else "Free"
    status = "Paused" if user["paused"] else "Active"

    await update.message.reply_html(
        "<b>Your Profile</b>\n\n"
        f"Skills:      {skills}\n"
        f"Location:    {location}\n"
        f"Experience:  {exp}\n"
        f"Plan:        {plan}\n"
        f"Status:      {status}"
    )

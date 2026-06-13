"""Command handlers: /start, /help, /status, /reset, /privacy."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.config import settings
from bot.database import SessionLocal, get_or_create_user
from bot.services import quota

WELCOME = (
    "👋 *Welcome to the AI Resume & Job Application Bot!*\n\n"
    "I help you tailor your resume to any job — right here in Telegram, in under "
    "a minute. Here's how it works:\n\n"
    "1️⃣  Upload your resume (PDF or DOCX)\n"
    "2️⃣  Paste the job description\n"
    "3️⃣  Pick: ✍️ Rewrite, 💌 Cover Letter, or ⚡ Both\n\n"
    "You'll get an *ATS score* (before vs. after) and a polished PDF to download.\n\n"
    f"🎁 Your first *{settings.free_rewrites} rewrites are free*.\n\n"
    "📎 *Go ahead — upload your resume to begin.*"
)

HELP = (
    "*How to use this bot*\n\n"
    "📎 Upload a resume (PDF/DOCX), then paste a job description.\n"
    "Then choose an action:\n"
    "• ✍️ *Rewrite Resume* — ATS-optimized rewrite matching the JD\n"
    "• 💌 *Cover Letter* — tailored, ready to send\n"
    "• ⚡ *Both*\n\n"
    "*Commands*\n"
    "/start — restart and see the welcome guide\n"
    "/status — check your remaining rewrites & plan\n"
    "/reset — clear the current resume & JD\n"
    "/privacy — how your data is handled\n"
    "/help — show this message"
)

PRIVACY = (
    "*Your privacy matters* 🔒\n\n"
    f"• Uploaded files are automatically deleted within "
    f"{settings.file_retention_hours} hours.\n"
    "• We never store your Telegram identity in the clear — your user ID is "
    "hashed before it touches our database.\n"
    "• Resume text is used only to generate your output and is not sold or "
    "shared.\n"
    "• All traffic is over encrypted connections."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    context.user_data["state"] = "awaiting_resume"
    async with SessionLocal() as session:
        await get_or_create_user(session, update.effective_user.id)
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP, parse_mode=ParseMode.MARKDOWN)


async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(PRIVACY, parse_mode=ParseMode.MARKDOWN)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        st = quota.status_for(user)

    if st.pro_active:
        plan_line = "💎 *Monthly Pro* — unlimited rewrites"
    else:
        bits = []
        if st.paid_credits:
            bits.append(f"{st.paid_credits} paid credit(s)")
        bits.append(f"{st.free_remaining} free rewrite(s) left")
        plan_line = "Plan: Free — " + ", ".join(bits)

    await update.message.reply_text(
        f"📊 *Your status*\n\n{plan_line}\n\nSend /start to tailor another resume.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    context.user_data["state"] = "awaiting_resume"
    await update.message.reply_text(
        "🧹 Cleared. Upload a resume (PDF/DOCX) to start fresh."
    )

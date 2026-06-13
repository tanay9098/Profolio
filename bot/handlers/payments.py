"""Paywall + payment handlers (PRD §5.1 Payment Flow, §8.2).

Two gateways:
  • Razorpay Payment Links — we generate a link, the user pays in-browser, and the
    Razorpay webhook (bot/webhook/server.py) credits the account automatically.
  • Telegram Stars — native in-chat checkout (XTR). Credited on successful_payment.
"""

from __future__ import annotations

import logging
import uuid

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.config import settings
from bot.database import Payment, SessionLocal, get_or_create_user, hash_user_id
from bot.handlers import keyboards
from bot.services import quota
from bot.services import razorpay_client
from bot.services.plans import PLANS, get_plan

logger = logging.getLogger(__name__)

STARS_PAYLOAD_PREFIX = "stars_purchase:"


def _paywall_text() -> str:
    lines = [
        "🚫 *You've used all your free rewrites.*",
        "",
        "Upgrade to keep tailoring resumes and generating cover letters:",
        "",
    ]
    for code, plan in PLANS.items():
        if code in ("pack5", "pack20", "pro"):
            lines.append(f"• *{plan.title}* — ₹{plan.price_inr}: {plan.description}")
    lines.append("")
    lines.append("Choose a plan to continue 👇")
    return "\n".join(lines)


async def show_paywall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = _paywall_text()
    markup = keyboards.paywall_keyboard()
    if update.callback_query:
        await update.callback_query.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup
        )
    else:
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup
        )


async def handle_plan_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    code = query.data[len(keyboards.PLAN_PREFIX):]

    if code == "_back":
        await query.message.edit_text(
            _paywall_text(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboards.paywall_keyboard(),
        )
        return

    plan = get_plan(code)
    if not plan:
        await query.answer("Unknown plan.", show_alert=True)
        return

    if not settings.razorpay_enabled and not settings.enable_telegram_stars:
        await query.message.reply_text(
            "⚠️ Payments aren't configured yet. Please try again later."
        )
        return

    await query.message.edit_text(
        f"*{plan.title}* — ₹{plan.price_inr}\n{plan.description}\n\n"
        "How would you like to pay?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboards.payment_method_keyboard(code),
    )


async def handle_razorpay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    code = query.data[len(keyboards.RZP_PREFIX):]
    plan = get_plan(code)
    if not plan:
        await query.answer("Unknown plan.", show_alert=True)
        return

    if not settings.razorpay_enabled:
        await query.message.reply_text("⚠️ Razorpay isn't configured.")
        return

    user_hash = hash_user_id(update.effective_user.id)
    reference_id = f"profolio_{uuid.uuid4().hex[:16]}"

    try:
        link = await razorpay_client.create_payment_link(plan, user_hash, reference_id)
    except Exception:  # noqa: BLE001
        logger.exception("Razorpay link creation failed")
        await query.message.reply_text(
            "⚠️ Couldn't create a payment link right now. Please try again."
        )
        return

    # Record a pending payment so the webhook can match & credit it.
    async with SessionLocal() as session:
        session.add(
            Payment(
                tg_user_hash=user_hash,
                plan_code=plan.code,
                amount_inr=plan.price_inr,
                provider="razorpay",
                provider_ref=reference_id,
                status="created",
                notify_chat_id=update.effective_chat.id,
            )
        )
        await session.commit()

    pay_url = link.get("short_url") or link.get("url")
    await query.message.reply_text(
        f"💳 *{plan.title}* — ₹{plan.price_inr}\n\n"
        "Tap below to pay securely via Razorpay. Your credits are added "
        "automatically once payment is confirmed.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("💳 Pay now", url=pay_url)]]
        ),
    )


async def handle_stars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    code = query.data[len(keyboards.STARS_PREFIX):]
    plan = get_plan(code)
    if not plan:
        await query.answer("Unknown plan.", show_alert=True)
        return

    if not settings.enable_telegram_stars:
        await query.message.reply_text("⚠️ Telegram Stars aren't enabled.")
        return

    # Telegram Stars (XTR) need no provider token; prices are in whole Stars.
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=plan.title,
        description=plan.description,
        payload=f"{STARS_PAYLOAD_PREFIX}{plan.code}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=plan.title, amount=plan.price_stars)],
    )


async def handle_pre_checkout(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.pre_checkout_query
    payload = query.invoice_payload or ""
    if payload.startswith(STARS_PAYLOAD_PREFIX):
        code = payload[len(STARS_PAYLOAD_PREFIX):]
        if get_plan(code):
            await query.answer(ok=True)
            return
    await query.answer(ok=False, error_message="This item is no longer available.")


async def handle_successful_payment(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    sp = update.message.successful_payment
    payload = sp.invoice_payload or ""
    if not payload.startswith(STARS_PAYLOAD_PREFIX):
        return
    code = payload[len(STARS_PAYLOAD_PREFIX):]
    plan = get_plan(code)
    if not plan:
        return

    user_hash = hash_user_id(update.effective_user.id)
    async with SessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        await quota.apply_purchase(session, user, plan)
        session.add(
            Payment(
                tg_user_hash=user_hash,
                plan_code=plan.code,
                amount_inr=plan.price_inr,
                provider="stars",
                provider_ref=sp.telegram_payment_charge_id,
                status="paid",
            )
        )
        await session.commit()
        st = quota.status_for(user)

    if st.pro_active:
        granted = "💎 Monthly Pro is active — unlimited rewrites!"
    else:
        granted = f"🎟️ You now have {st.paid_credits} rewrite credit(s)."

    await update.message.reply_text(
        f"✅ *Payment received — thank you!*\n\n{granted}\n\n"
        "Paste a job description to keep tailoring, or /start over.",
        parse_mode=ParseMode.MARKDOWN,
    )

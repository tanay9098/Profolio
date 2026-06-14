"""Inline keyboards and callback-data constants shared across handlers.

Callback-data scheme (kept short — Telegram caps callback_data at 64 bytes):
    act:rewrite | act:cover | act:both     -> run an AI action
    plan:<code>                            -> a paywall plan was chosen
    rzp:<code>                             -> pay this plan via Razorpay
    stars:<code>                           -> pay this plan via Telegram Stars
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings
from bot.services.plans import PAYWALL_PLANS, PLANS

# --- callback-data prefixes ---
ACT_REWRITE = "act:rewrite"
ACT_COVER = "act:cover"
ACT_BOTH = "act:both"
PLAN_PREFIX = "plan:"
RZP_PREFIX = "rzp:"
STARS_PREFIX = "stars:"


def actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✍️ Rewrite Resume", callback_data=ACT_REWRITE)],
            [InlineKeyboardButton("💌 Generate Cover Letter", callback_data=ACT_COVER)],
            [InlineKeyboardButton("⚡ Both", callback_data=ACT_BOTH)],
        ]
    )


def paywall_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for code in PAYWALL_PLANS:
        plan = PLANS[code]
        rows.append(
            [
                InlineKeyboardButton(
                    f"{plan.title} — ₹{plan.price_inr}",
                    callback_data=f"{PLAN_PREFIX}{code}",
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


def payment_method_keyboard(plan_code: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if settings.razorpay_enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    "💳 Pay with Razorpay (₹)",
                    callback_data=f"{RZP_PREFIX}{plan_code}",
                )
            ]
        )
    if settings.enable_telegram_stars:
        rows.append(
            [
                InlineKeyboardButton(
                    "⭐ Pay with Telegram Stars",
                    callback_data=f"{STARS_PREFIX}{plan_code}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("« Back to plans", callback_data="plan:_back")])
    return InlineKeyboardMarkup(rows)

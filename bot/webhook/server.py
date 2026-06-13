"""Razorpay webhook server (PRD §8.2: auto-quota update on webhook confirmation).

Runs in-process alongside the Telegram bot (shares the same event loop). On a
verified `payment_link.paid` / `payment.captured` event we mark the pending
Payment row paid, credit the user's quota, and message them via the bot.

Endpoints:
    POST /razorpay/webhook   — Razorpay posts events here (HMAC-verified)
    GET  /razorpay/return    — browser redirect target after payment
    GET  /health             — liveness probe
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from aiohttp import web
from sqlalchemy import select
from telegram import Bot
from telegram.constants import ParseMode

from bot.config import settings
from bot.database import Payment, SessionLocal, get_user_by_hash
from bot.services import quota
from bot.services.plans import get_plan

logger = logging.getLogger(__name__)


def _verify_signature(body: bytes, signature: str) -> bool:
    if not settings.razorpay_webhook_secret:
        logger.warning("RAZORPAY_WEBHOOK_SECRET not set — rejecting webhook")
        return False
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _extract_reference_id(payload: dict) -> str | None:
    """Pull our reference_id out of whichever entity the event carries."""
    entities = payload.get("payload", {})
    for key in ("payment_link", "payment", "order"):
        entity = entities.get(key, {}).get("entity", {})
        if not entity:
            continue
        ref = entity.get("reference_id")
        if ref:
            return ref
        notes = entity.get("notes") or {}
        if notes.get("reference_id"):
            return notes["reference_id"]
    return None


async def _credit_payment(bot: Bot, reference_id: str) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Payment).where(Payment.provider_ref == reference_id)
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            logger.warning("Webhook for unknown reference_id=%s", reference_id)
            return
        if payment.status == "paid":
            return  # idempotent — already credited

        plan = get_plan(payment.plan_code)
        user = await get_user_by_hash(session, payment.tg_user_hash)
        if plan is None or user is None:
            logger.error("Cannot credit payment %s (missing plan/user)", reference_id)
            return

        await quota.apply_purchase(session, user, plan)
        payment.status = "paid"
        chat_id = payment.notify_chat_id
        payment.notify_chat_id = None  # don't retain longer than needed
        await session.commit()
        st = quota.status_for(user)

    if chat_id is None:
        return
    if st.pro_active:
        granted = "💎 Monthly Pro is active — unlimited rewrites!"
    else:
        granted = f"🎟️ You now have {st.paid_credits} rewrite credit(s)."
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ *Payment received — thank you!*\n\n{granted}\n\n"
                "Paste a job description to keep tailoring, or /start over."
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to notify user after payment")


async def _handle_webhook(request: web.Request) -> web.Response:
    body = await request.read()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not _verify_signature(body, signature):
        return web.Response(status=400, text="invalid signature")

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return web.Response(status=400, text="invalid json")

    event = payload.get("event", "")
    if event in ("payment_link.paid", "payment.captured", "order.paid"):
        reference_id = _extract_reference_id(payload)
        if reference_id:
            bot: Bot = request.app["bot"]
            await _credit_payment(bot, reference_id)

    # Always 200 quickly so Razorpay doesn't retry a handled event.
    return web.Response(status=200, text="ok")


async def _handle_return(request: web.Request) -> web.Response:
    return web.Response(
        content_type="text/html",
        text=(
            "<html><body style='font-family:sans-serif;text-align:center;"
            "padding-top:60px'><h2>✅ Payment complete</h2>"
            "<p>You can close this tab and return to Telegram — "
            "your credits have been added.</p></body></html>"
        ),
    )


async def _handle_health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


def build_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/razorpay/webhook", _handle_webhook)
    app.router.add_get("/razorpay/return", _handle_return)
    app.router.add_get("/health", _handle_health)
    return app


async def start_webhook_server(bot: Bot) -> web.AppRunner:
    """Start the aiohttp server on the configured host/port. Returns the runner."""
    app = build_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.webhook_host, settings.webhook_port)
    await site.start()
    logger.info(
        "Razorpay webhook server listening on %s:%s",
        settings.webhook_host,
        settings.webhook_port,
    )
    return runner

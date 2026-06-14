"""Razorpay Payment Links (PRD §8.2).

We generate a Payment Link per transaction with `notes` carrying the user hash
and plan code, so the webhook can credit the right user on confirmation. All
network calls run in a thread (the razorpay SDK is synchronous).
"""

from __future__ import annotations

import asyncio
import logging

from bot.config import settings
from bot.services.plans import Plan

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        import razorpay

        _client = razorpay.Client(
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
        )
    return _client


def _create_link_sync(plan: Plan, tg_user_hash: str, reference_id: str) -> dict:
    client = _get_client()
    payload = {
        "amount": plan.price_inr * 100,  # paise
        "currency": "INR",
        "accept_partial": False,
        "reference_id": reference_id,
        "description": f"{plan.title} — AI Resume Bot",
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "notes": {
            "tg_user_hash": tg_user_hash,
            "plan_code": plan.code,
            "reference_id": reference_id,
        },
        "callback_method": "get",
    }
    if settings.public_base_url:
        payload["callback_url"] = f"{settings.public_base_url}/razorpay/return"
    return client.payment_link.create(payload)


async def create_payment_link(plan: Plan, tg_user_hash: str, reference_id: str) -> dict:
    """Create a Razorpay payment link. Returns the API response dict."""
    return await asyncio.to_thread(_create_link_sync, plan, tg_user_hash, reference_id)

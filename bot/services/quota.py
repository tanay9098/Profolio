"""Quota management (PRD §5.1 "Usage Limits": 3 free rewrites, then paywall).

Quota precedence when consuming a rewrite:
  1. Active Pro subscription  -> unlimited, nothing decremented.
  2. Paid credits remaining   -> decrement paid_credits.
  3. Free allowance remaining -> increment free_used.
  4. Otherwise                -> blocked (caller shows the paywall).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database import User
from bot.services.plans import Plan


@dataclass
class QuotaStatus:
    allowed: bool
    reason: str  # "pro" | "paid" | "free" | "blocked"
    free_remaining: int
    paid_credits: int
    pro_active: bool


def status_for(user: User) -> QuotaStatus:
    pro = user.pro_active()
    free_remaining = max(0, settings.free_rewrites - user.free_used)
    if pro:
        reason = "pro"
        allowed = True
    elif user.paid_credits > 0:
        reason = "paid"
        allowed = True
    elif free_remaining > 0:
        reason = "free"
        allowed = True
    else:
        reason = "blocked"
        allowed = False
    return QuotaStatus(
        allowed=allowed,
        reason=reason,
        free_remaining=free_remaining,
        paid_credits=user.paid_credits,
        pro_active=pro,
    )


async def consume_rewrite(session: AsyncSession, user: User) -> QuotaStatus:
    """Atomically consume one rewrite unit. Returns the post-consume status.

    The caller must check `.allowed` BEFORE doing paid work; this commits the
    decrement only when a unit was actually available.
    """
    status = status_for(user)
    if not status.allowed:
        return status

    if status.reason == "pro":
        pass  # unlimited
    elif status.reason == "paid":
        user.paid_credits -= 1
    elif status.reason == "free":
        user.free_used += 1

    await session.commit()
    await session.refresh(user)
    return status_for(user)


async def apply_purchase(session: AsyncSession, user: User, plan: Plan) -> None:
    """Credit a successful purchase to the user."""
    if plan.credits is not None:
        user.paid_credits += plan.credits
    if plan.pro_days is not None:
        now = dt.datetime.now(dt.timezone.utc)
        base = now
        if user.pro_active(now) and user.pro_expires_at is not None:
            existing = user.pro_expires_at
            if existing.tzinfo is None:
                existing = existing.replace(tzinfo=dt.timezone.utc)
            base = max(now, existing)
        user.is_pro = True
        user.pro_expires_at = base + dt.timedelta(days=plan.pro_days)
    await session.commit()
    await session.refresh(user)

"""Pricing plans (PRD §8.1).

A single source of truth for the freemium / pay-per-use / subscription tiers so
the paywall, payment links, and quota crediting all agree.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    code: str
    title: str
    price_inr: int
    # Number of rewrite credits granted (None => unlimited / subscription).
    credits: int | None
    # If set, grants unlimited use for this many days (subscription).
    pro_days: int | None
    description: str

    @property
    def price_stars(self) -> int:
        """Approximate Telegram Stars price.

        Telegram Stars are a separate currency; this is a simple, transparent
        conversion (~₹1 ≈ 1 Star) suitable for the India launch. Tune to taste.
        """
        return max(1, self.price_inr)


PLANS: dict[str, Plan] = {
    "pack5": Plan(
        code="pack5",
        title="Rewrite Pack (5)",
        price_inr=99,
        credits=5,
        pro_days=None,
        description="5 rewrites, cover letters, PDF download",
    ),
    "pack20": Plan(
        code="pack20",
        title="Rewrite Pack (20)",
        price_inr=299,
        credits=20,
        pro_days=None,
        description="20 rewrites + priority processing",
    ),
    "pro": Plan(
        code="pro",
        title="Monthly Pro",
        price_inr=499,
        credits=None,
        pro_days=30,
        description="Unlimited rewrites, all features, for 30 days",
    ),
}

# Plans offered in the paywall, in display order.
PAYWALL_PLANS = ["pack5", "pack20", "pro"]


def get_plan(code: str) -> Plan | None:
    return PLANS.get(code)

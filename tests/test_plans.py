"""Tests for pricing plan definitions (PRD §8.1)."""

from bot.services import plans


def test_paywall_plans_exist():
    for code in plans.PAYWALL_PLANS:
        assert plans.get_plan(code) is not None


def test_pack_prices_match_prd():
    assert plans.PLANS["pack5"].price_inr == 99
    assert plans.PLANS["pack20"].price_inr == 299
    assert plans.PLANS["pro"].price_inr == 499


def test_pack_credits():
    assert plans.PLANS["pack5"].credits == 5
    assert plans.PLANS["pack20"].credits == 20
    assert plans.PLANS["pro"].credits is None  # unlimited subscription
    assert plans.PLANS["pro"].pro_days == 30


def test_unknown_plan_returns_none():
    assert plans.get_plan("does-not-exist") is None

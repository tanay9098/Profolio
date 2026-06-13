"""Tests for quota precedence and purchase crediting (PRD §5.1, §8.1)."""

import asyncio
import datetime as dt

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.config import settings
from bot.database import Base, User
from bot.services import quota
from bot.services.plans import PLANS


def _make_user(**kw) -> User:
    u = User()
    u.free_used = kw.get("free_used", 0)
    u.paid_credits = kw.get("paid_credits", 0)
    u.is_pro = kw.get("is_pro", False)
    u.pro_expires_at = kw.get("pro_expires_at", None)
    return u


def test_fresh_user_is_on_free_tier():
    st = quota.status_for(_make_user())
    assert st.allowed
    assert st.reason == "free"
    assert st.free_remaining == settings.free_rewrites


def test_exhausted_free_user_is_blocked():
    st = quota.status_for(_make_user(free_used=settings.free_rewrites))
    assert not st.allowed
    assert st.reason == "blocked"


def test_paid_credits_take_precedence_over_free():
    st = quota.status_for(_make_user(free_used=settings.free_rewrites, paid_credits=3))
    assert st.allowed
    assert st.reason == "paid"


def test_active_pro_is_unlimited():
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=10)
    st = quota.status_for(
        _make_user(free_used=99, is_pro=True, pro_expires_at=future)
    )
    assert st.allowed
    assert st.reason == "pro"


def test_expired_pro_falls_back():
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    st = quota.status_for(
        _make_user(free_used=settings.free_rewrites, is_pro=True, pro_expires_at=past)
    )
    assert not st.allowed


def test_apply_purchase_credits_and_consume():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)

        async with maker() as session:
            user = User(tg_user_hash="testhash")
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # Buy a 5-pack -> 5 paid credits.
            await quota.apply_purchase(session, user, PLANS["pack5"])
            assert user.paid_credits == 5

            # Consume one -> 4 left, reason paid.
            post = await quota.consume_rewrite(session, user)
            assert user.paid_credits == 4
            assert post.reason in ("paid", "free")

            # Buy Pro -> unlimited.
            await quota.apply_purchase(session, user, PLANS["pro"])
            assert user.pro_active()

        await engine.dispose()

    asyncio.run(run())

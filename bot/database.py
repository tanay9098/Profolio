"""Database layer: SQLAlchemy 2.0 async models + session factory.

Privacy (PRD §7.3): we never store the raw Telegram user_id. Instead we store a
salted SHA-256 hash of it (`tg_user_hash`). The bot keeps the raw id only in
memory for the duration of a request to send replies.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bot.config import settings


# --------------------------------------------------------------------------- #
# Engine / session                                                            #
# --------------------------------------------------------------------------- #
engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


def hash_user_id(tg_user_id: int) -> str:
    """Pseudonymise a Telegram user id with the configured salt (PRD §7.3)."""
    salted = f"{settings.user_id_hash_salt}:{tg_user_id}".encode()
    return hashlib.sha256(salted).hexdigest()


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --------------------------------------------------------------------------- #
# Models                                                                      #
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_user_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Lifetime count of free rewrites already consumed.
    free_used: Mapped[int] = mapped_column(Integer, default=0)
    # Paid rewrite credits remaining (from packs).
    paid_credits: Mapped[int] = mapped_column(Integer, default=0)

    # Unlimited subscription state.
    is_pro: Mapped[bool] = mapped_column(Boolean, default=False)
    pro_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def pro_active(self, now: dt.datetime | None = None) -> bool:
        if not self.is_pro:
            return False
        if self.pro_expires_at is None:
            return True
        now = now or _utcnow()
        # pro_expires_at may be naive when read back from SQLite; normalise.
        expires = self.pro_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.timezone.utc)
        return expires > now


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_user_hash: Mapped[str] = mapped_column(String(64), index=True)
    plan_code: Mapped[str] = mapped_column(String(32))
    amount_inr: Mapped[int] = mapped_column(Integer)  # rupees
    provider: Mapped[str] = mapped_column(String(16))  # "razorpay" | "stars"
    provider_ref: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(16), default="created")  # created|paid|failed
    # Transient: lets the async Razorpay webhook deliver the confirmation message.
    # Cleared once the payment is credited.
    notify_chat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_or_create_user(session: AsyncSession, tg_user_id: int) -> User:
    user_hash = hash_user_id(tg_user_id)
    result = await session.execute(select(User).where(User.tg_user_hash == user_hash))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(tg_user_hash=user_hash)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_user_by_hash(session: AsyncSession, user_hash: str) -> User | None:
    result = await session.execute(select(User).where(User.tg_user_hash == user_hash))
    return result.scalar_one_or_none()

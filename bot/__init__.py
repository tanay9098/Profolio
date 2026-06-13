"""AI Resume & Job Application Bot — a Telegram-native career assistant.

Package layout:
    bot.config        Settings loaded from environment.
    bot.database      SQLAlchemy models + async session factory.
    bot.handlers      Telegram update handlers (the conversation flow).
    bot.services      Business logic: parsing, AI, ATS scoring, PDF, quota, payments.
    bot.webhook       aiohttp server for Razorpay payment confirmations.
    bot.main          Entry point that wires everything together.
"""

__version__ = "1.0.0"

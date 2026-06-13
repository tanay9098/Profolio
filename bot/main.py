"""Entry point: wire handlers, start the webhook server, run the bot.

Run with:  python -m bot.main
"""

from __future__ import annotations

import datetime as dt
import logging

from telegram import Update
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from bot.config import settings
from bot.database import init_db
from bot.handlers import commands, flow, keyboards, payments
from bot.services import files as file_svc
from bot.webhook.server import start_webhook_server

logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
)
logger = logging.getLogger("profolio")


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error processing update", exc_info=context.error)


async def _cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    file_svc.cleanup_expired()


async def _post_init(application: Application) -> None:
    settings.ensure_dirs()
    await init_db()

    # Start the Razorpay webhook server on the same event loop.
    if settings.razorpay_enabled:
        runner = await start_webhook_server(application.bot)
        application.bot_data["webhook_runner"] = runner
    else:
        logger.info("Razorpay not configured — webhook server not started.")

    # Periodic retention cleanup (PRD §7.3).
    if application.job_queue:
        application.job_queue.run_repeating(
            _cleanup_job, interval=3600, first=dt.timedelta(minutes=5)
        )

    await application.bot.set_my_commands(
        [
            ("start", "Start / restart and see the guide"),
            ("status", "Check remaining rewrites & plan"),
            ("reset", "Clear current resume & JD"),
            ("privacy", "How your data is handled"),
            ("help", "Help"),
        ]
    )
    logger.info("Bot initialised. Model=%s", settings.anthropic_model)


async def _post_shutdown(application: Application) -> None:
    runner = application.bot_data.get("webhook_runner")
    if runner is not None:
        await runner.cleanup()


def build_application() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. See .env.example.")
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY is not set — AI actions will fail.")

    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .rate_limiter(AIORateLimiter())
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    # --- commands ---
    application.add_handler(CommandHandler("start", commands.start))
    application.add_handler(CommandHandler("help", commands.help_command))
    application.add_handler(CommandHandler("status", commands.status))
    application.add_handler(CommandHandler("reset", commands.reset))
    application.add_handler(CommandHandler("privacy", commands.privacy))

    # --- core flow ---
    application.add_handler(MessageHandler(filters.Document.ALL, flow.handle_document))
    application.add_handler(
        CallbackQueryHandler(flow.handle_action, pattern=r"^act:")
    )

    # --- payments ---
    application.add_handler(
        CallbackQueryHandler(
            payments.handle_plan_selection, pattern=rf"^{keyboards.PLAN_PREFIX}"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            payments.handle_razorpay, pattern=rf"^{keyboards.RZP_PREFIX}"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            payments.handle_stars, pattern=rf"^{keyboards.STARS_PREFIX}"
        )
    )
    application.add_handler(PreCheckoutQueryHandler(payments.handle_pre_checkout))
    application.add_handler(
        MessageHandler(
            filters.SUCCESSFUL_PAYMENT, payments.handle_successful_payment
        )
    )

    # --- free text (treated as the job description) ---
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, flow.handle_text)
    )

    application.add_error_handler(_on_error)
    return application


def main() -> None:
    application = build_application()
    logger.info("Starting AI Resume Bot (polling)…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

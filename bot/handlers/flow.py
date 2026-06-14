"""Core rewrite flow (PRD §6.1): upload → JD → action → ATS score + PDF.

State is kept per-user in `context.user_data`:
    state        : "awaiting_resume" | "awaiting_jd" | "ready"
    resume_text  : extracted resume text
    resume_name  : original filename
    jd_text      : pasted job description
    ats_before   : AtsResult computed when the JD arrives (free teaser)
"""

from __future__ import annotations

import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from bot.database import SessionLocal, get_or_create_user, hash_user_id
from bot.handlers import keyboards
from bot.handlers.payments import show_paywall
from bot.services import ai, ats, parsing, pdf
from bot.services import files as file_svc
from bot.services import quota

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB safety cap


# --------------------------------------------------------------------------- #
# Step 1-2: resume upload                                                     #
# --------------------------------------------------------------------------- #
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    name = (doc.file_name or "resume").lower()
    if not (name.endswith(".pdf") or name.endswith(".docx") or name.endswith(".doc")):
        await update.message.reply_text(
            "❗ Please upload your resume as a *PDF* or *DOCX* file.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if doc.file_size and doc.file_size > MAX_FILE_BYTES:
        await update.message.reply_text(
            "❗ That file is too large (max 15 MB). Please upload a smaller PDF/DOCX."
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    user_hash = hash_user_id(update.effective_user.id)
    dest_dir = file_svc.user_dir(user_hash)
    suffix = Path(name).suffix or ".pdf"
    dest = dest_dir / f"resume{suffix}"

    try:
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(custom_path=str(dest))
        resume_text = parsing.extract_text(dest)
    except parsing.UnsupportedFileError as exc:
        await update.message.reply_text(f"❗ {exc}")
        return
    except Exception:  # noqa: BLE001
        logger.exception("Failed to parse uploaded resume")
        await update.message.reply_text(
            "⚠️ I couldn't read that file. Please re-upload a valid PDF or DOCX."
        )
        return
    finally:
        # We only need the text; remove the original promptly (privacy §7.3).
        file_svc.safe_unlink(dest)

    if parsing.looks_empty(resume_text):
        await update.message.reply_text(
            "⚠️ I couldn't extract text from that file — it may be a *scanned image*.\n"
            "Please upload a text-based PDF or a DOCX export.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    context.user_data["resume_text"] = resume_text
    context.user_data["resume_name"] = doc.file_name
    context.user_data["state"] = "awaiting_jd"
    context.user_data.pop("jd_text", None)
    context.user_data.pop("ats_before", None)

    await update.message.reply_text(
        "✅ Got your resume!\n\n"
        "📋 Now *paste the job description* you're applying for (as a text message).",
        parse_mode=ParseMode.MARKDOWN,
    )


# --------------------------------------------------------------------------- #
# Step 3-4: job description                                                   #
# --------------------------------------------------------------------------- #
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()

    if not context.user_data.get("resume_text"):
        await update.message.reply_text(
            "👋 Let's start — please *upload your resume* (PDF or DOCX) first.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if len(text) < 40:
        await update.message.reply_text(
            "📋 That looks a bit short for a job description. Please paste the full "
            "JD text so I can tailor your resume accurately."
        )
        return

    context.user_data["jd_text"] = text
    context.user_data["state"] = "ready"

    # Free teaser: compute the "before" ATS score immediately (drives conversion).
    before = ats.score_resume(context.user_data["resume_text"], text)
    context.user_data["ats_before"] = before

    missing = ", ".join(before.missing_keywords[:6]) or "—"
    await update.message.reply_text(
        f"📊 *Current ATS match: {before.score}/100*\n\n"
        f"🔍 Missing keywords: _{missing}_\n\n"
        "Choose what you'd like me to do 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboards.actions_keyboard(),
    )


# --------------------------------------------------------------------------- #
# Step 5-7: run the selected action                                           #
# --------------------------------------------------------------------------- #
async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data  # act:rewrite | act:cover | act:both

    resume_text = context.user_data.get("resume_text")
    jd_text = context.user_data.get("jd_text")
    if not resume_text or not jd_text:
        await query.message.reply_text(
            "Your session expired. Send /start and upload your resume again."
        )
        return

    # --- quota check (consume one unit up front) ---
    async with SessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        pre = quota.status_for(user)
        if not pre.allowed:
            await show_paywall(update, context)
            return
        post = await quota.consume_rewrite(session, user)

    await query.message.chat.send_action(ChatAction.TYPING)
    progress = await query.message.reply_text("⏳ Working on it… this takes ~20–30s.")

    user_hash = hash_user_id(update.effective_user.id)
    out_dir = file_svc.user_dir(user_hash)
    produced: list[Path] = []

    try:
        do_rewrite = action in (keyboards.ACT_REWRITE, keyboards.ACT_BOTH)
        do_cover = action in (keyboards.ACT_COVER, keyboards.ACT_BOTH)

        summary_lines: list[str] = []

        if do_rewrite:
            rewritten = await ai.rewrite_resume(resume_text, jd_text)
            after = ats.score_resume(rewritten, jd_text)
            before = context.user_data.get("ats_before")
            before_score = before.score if before else None

            pdf_path = out_dir / "rewritten_resume.pdf"
            pdf.render_text_to_pdf(rewritten, pdf_path, doc_title="Resume")
            produced.append(pdf_path)

            if before_score is not None:
                delta = after.score - before_score
                arrow = "▲" if delta >= 0 else "▼"
                summary_lines.append(
                    f"📈 *ATS score: {before_score} → {after.score}/100* "
                    f"({arrow}{abs(delta)})"
                )
            else:
                summary_lines.append(f"📈 *ATS score: {after.score}/100*")

            if after.suggestions:
                tips = "\n".join(f"• {s}" for s in after.suggestions[:3])
                summary_lines.append(f"\n💡 *Tips:*\n{tips}")

        if do_cover:
            cover = await ai.generate_cover_letter(resume_text, jd_text)
            cover_path = out_dir / "cover_letter.pdf"
            pdf.render_text_to_pdf(cover, cover_path, doc_title="Cover Letter")
            produced.append(cover_path)
            summary_lines.append("💌 Cover letter ready.")

        # --- deliver outputs ---
        await progress.delete()
        for path in produced:
            with path.open("rb") as fh:
                await query.message.reply_document(
                    document=fh, filename=path.name
                )

        # remaining-quota footer
        if post.pro_active:
            footer = "💎 Monthly Pro — unlimited rewrites."
        elif post.paid_credits > 0:
            footer = f"🎟️ {post.paid_credits} paid credit(s) left."
        else:
            footer = f"🎁 {post.free_remaining} free rewrite(s) left."

        summary = "\n".join(summary_lines) if summary_lines else "Done!"
        await query.message.reply_text(
            f"✅ *Done!*\n\n{summary}\n\n{footer}\n\n"
            "Paste another job description to tailor again, or /start over.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboards.actions_keyboard(),
        )

    except Exception:  # noqa: BLE001
        logger.exception("Action processing failed")
        # Refund the consumed unit on failure so users aren't charged for errors.
        async with SessionLocal() as session:
            user = await get_or_create_user(session, update.effective_user.id)
            await _refund(session, user, pre)
        try:
            await progress.edit_text(
                "⚠️ Something went wrong while generating your output. "
                "Your rewrite was *not* counted. Please try again.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:  # noqa: BLE001
            await query.message.reply_text(
                "⚠️ Something went wrong. Your rewrite was not counted. Try again."
            )
    finally:
        for path in produced:
            file_svc.safe_unlink(path)


async def _refund(session, user, pre: quota.QuotaStatus) -> None:
    """Return the unit consumed before a failed action."""
    if pre.reason == "free" and user.free_used > 0:
        user.free_used -= 1
    elif pre.reason == "paid":
        user.paid_credits += 1
    # pro: nothing was decremented.
    await session.commit()

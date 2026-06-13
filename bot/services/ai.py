"""AI backend — resume rewriting and cover-letter generation via the Claude API.

Uses the official Anthropic async SDK. Model and effort are configurable
(`ANTHROPIC_MODEL`, `ANTHROPIC_EFFORT`); we default to claude-opus-4-8.

Prompts are tuned for the PRD's core job: rewrite resume sections to match JD
keywords (truthfully — no fabrication) and produce a tailored cover letter.
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from bot.config import settings

logger = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


# Trim very large inputs so we stay within sane token budgets (and cost limits,
# per the §9 risk table). Resumes/JDs rarely exceed this.
_MAX_RESUME_CHARS = 16_000
_MAX_JD_CHARS = 12_000


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n…[truncated]"


REWRITE_SYSTEM = (
    "You are an expert resume writer and ATS optimization specialist for the "
    "Indian job market. You rewrite resumes to maximize Applicant Tracking "
    "System (ATS) compatibility for a specific job description.\n\n"
    "Hard rules:\n"
    "- NEVER fabricate experience, employers, dates, degrees, or metrics. Only "
    "rephrase, reorganize, and surface what the candidate already has.\n"
    "- Naturally weave in relevant keywords and skills from the job description "
    "where they truthfully apply.\n"
    "- Lead bullet points with strong action verbs; quantify impact where the "
    "candidate provided numbers.\n"
    "- Use clean, ATS-parseable plain text: clear SECTION HEADERS in caps, "
    "'- ' for bullets, no tables, no columns, no graphics.\n"
    "- Keep it concise and truthful. Output ONLY the rewritten resume text — no "
    "preamble, no commentary, no markdown fences."
)

COVER_LETTER_SYSTEM = (
    "You are an expert career writer for the Indian job market. You write "
    "concise, personalized, professional cover letters tailored to a specific "
    "job description and the candidate's actual resume.\n\n"
    "Hard rules:\n"
    "- NEVER fabricate experience or credentials the resume doesn't support.\n"
    "- 250-350 words, 3-4 short paragraphs, warm but professional.\n"
    "- Open with genuine interest, connect the candidate's real strengths to the "
    "role's needs, close with a clear call to action.\n"
    "- Output ONLY the cover letter body text — no preamble, no markdown fences, "
    "no placeholders like [Your Name] unless the name is unknown."
)


async def _complete(system: str, user: str, max_tokens: int = 4000) -> str:
    client = _get_client()
    # Stream and collect — robust against long outputs / request timeouts.
    async with client.messages.stream(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        system=system,
        output_config={"effort": settings.anthropic_effort},
        messages=[{"role": "user", "content": user}],
    ) as stream:
        message = await stream.get_final_message()

    parts = [block.text for block in message.content if block.type == "text"]
    text = "\n".join(parts).strip()
    if not text:
        raise RuntimeError("Empty response from AI model")
    return text


async def rewrite_resume(resume_text: str, jd_text: str) -> str:
    user = (
        "Rewrite the following resume to be ATS-optimized for the target job "
        "description.\n\n"
        "=== JOB DESCRIPTION ===\n"
        f"{_clip(jd_text, _MAX_JD_CHARS)}\n\n"
        "=== CURRENT RESUME ===\n"
        f"{_clip(resume_text, _MAX_RESUME_CHARS)}\n\n"
        "Return the full rewritten resume as clean plain text."
    )
    return await _complete(REWRITE_SYSTEM, user, max_tokens=4000)


async def generate_cover_letter(resume_text: str, jd_text: str) -> str:
    user = (
        "Write a tailored cover letter for this candidate and role.\n\n"
        "=== JOB DESCRIPTION ===\n"
        f"{_clip(jd_text, _MAX_JD_CHARS)}\n\n"
        "=== CANDIDATE RESUME ===\n"
        f"{_clip(resume_text, _MAX_RESUME_CHARS)}\n\n"
        "Return only the cover letter body."
    )
    return await _complete(COVER_LETTER_SYSTEM, user, max_tokens=1500)

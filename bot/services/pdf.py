"""PDF output generation (PRD §5.1 "Download Output").

Renders the AI-rewritten resume (or cover letter) plain text into a clean,
ATS-friendly single-column PDF using reportlab. Section headers in ALL CAPS are
detected and bolded; '- ' lines become bullets.
"""

from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

_HEADER_RE = re.compile(r"^[A-Z][A-Z0-9 &/().,'-]{2,}$")


def _styles():
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
        spaceAfter=2,
    )
    header = ParagraphStyle(
        "SectionHeader",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        spaceBefore=8,
        spaceAfter=4,
        textColor="#1F3864",
    )
    title = ParagraphStyle(
        "DocTitle",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        spaceAfter=6,
    )
    return body, header, title


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def render_text_to_pdf(text: str, out_path: Path, doc_title: str | None = None) -> Path:
    body, header, title = _styles()
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=doc_title or "Resume",
    )

    flow = []
    if doc_title:
        flow.append(Paragraph(_escape(doc_title), title))
        flow.append(Spacer(1, 4))

    pending_bullets: list[str] = []

    def flush_bullets() -> None:
        if pending_bullets:
            items = [
                ListItem(Paragraph(_escape(b), body), leftIndent=6)
                for b in pending_bullets
            ]
            flow.append(ListFlowable(items, bulletType="bullet", start="•"))
            pending_bullets.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_bullets()
            flow.append(Spacer(1, 4))
            continue

        bullet_match = re.match(r"^[-•*▪◦]\s+(.*)$", stripped)
        if bullet_match:
            pending_bullets.append(bullet_match.group(1))
            continue

        flush_bullets()
        if _HEADER_RE.match(stripped) and len(stripped.split()) <= 6:
            flow.append(Paragraph(_escape(stripped), header))
        else:
            flow.append(Paragraph(_escape(stripped), body))

    flush_bullets()
    doc.build(flow)
    return out_path

"""ATS (Applicant Tracking System) scoring (PRD §7.2).

Algorithm:
  1. Extract keywords from the JD (skills, tools, qualifications) via tokenisation
     + a curated skills lexicon + TF-IDF weighting.
  2. Compare against the resume using keyword overlap + TF-IDF cosine similarity.
  3. Penalise: missing action verbs, passive voice, non-quantified achievements.
  4. Output: a 0-100 score, the list of missing keywords, and suggestions.

This is intentionally transparent and dependency-light (scikit-learn only) rather
than a heavy embedding model — it runs in milliseconds per request, which matters
for the §3 "under 60 seconds" goal and the §9 API-cost risk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# --------------------------------------------------------------------------- #
# Lexicons                                                                     #
# --------------------------------------------------------------------------- #
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with",
    "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "we", "you", "your", "our",
    "will", "shall", "should", "would", "can", "could", "may", "might", "must",
    "have", "has", "had", "do", "does", "did", "not", "no", "yes", "if", "then",
    "than", "so", "such", "into", "over", "under", "about", "their", "they",
    "who", "what", "which", "when", "where", "how", "all", "any", "more", "most",
    "other", "some", "etc", "via", "per", "across", "within", "including",
    "role", "job", "work", "team", "company", "candidate", "position", "years",
    "year", "experience", "responsibilities", "requirements", "preferred",
    "plus", "ability", "strong", "good", "excellent", "looking", "join",
}

# Strong action verbs that ATS-friendly resumes lead bullets with.
ACTION_VERBS = {
    "led", "built", "designed", "developed", "implemented", "launched",
    "created", "improved", "increased", "reduced", "optimized", "managed",
    "delivered", "drove", "owned", "architected", "automated", "scaled",
    "shipped", "spearheaded", "established", "engineered", "streamlined",
    "achieved", "generated", "grew", "cut", "boosted", "accelerated",
    "negotiated", "coordinated", "mentored", "analyzed", "migrated",
}

# Common passive-voice markers (rough heuristic).
PASSIVE_RE = re.compile(
    r"\b(was|were|been|being|is|are)\s+\w+(ed|en)\b", re.IGNORECASE
)
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]{1,}")
NUMBER_RE = re.compile(r"\b\d+(\.\d+)?%?\b|\b(₹|\$|rs\.?)\s?\d", re.IGNORECASE)


@dataclass
class AtsResult:
    score: int  # 0-100
    keyword_overlap: float  # 0-1
    semantic_similarity: float  # 0-1
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "")]


def _content_terms(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def extract_jd_keywords(jd_text: str, top_n: int = 25) -> list[str]:
    """Return the most salient JD terms (skills, tools, qualifications).

    TF-IDF needs a corpus to be meaningful; for a single JD we rank by raw
    frequency, breaking ties by first-appearance order (Counter preserves
    insertion order), which keeps prominently-listed skills near the top.
    Numeric-only tokens are dropped.
    """
    from collections import Counter

    terms = [
        t
        for t in _content_terms(_tokens(jd_text))
        if not t.isdigit()
    ]
    if not terms:
        return []
    counter = Counter(terms)
    return [word for word, _ in counter.most_common(top_n)]


def _semantic_similarity(resume: str, jd: str) -> float:
    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        matrix = vectorizer.fit_transform([resume or "", jd or ""])
        sim = cosine_similarity(matrix[0:1], matrix[1:2])[0][0]
        return float(np.clip(sim, 0.0, 1.0))
    except ValueError:
        return 0.0


def _quality_penalties(resume: str) -> tuple[float, list[str]]:
    """Return (penalty 0-1, suggestions). Penalises weak resume writing."""
    suggestions: list[str] = []
    penalty = 0.0

    lines = [ln.strip() for ln in resume.splitlines() if ln.strip()]
    bullet_lines = [ln for ln in lines if re.match(r"^[-•*▪◦]", ln)] or lines

    # Missing action verbs.
    verb_starts = sum(
        1
        for ln in bullet_lines
        if (_tokens(ln) and _tokens(ln)[0] in ACTION_VERBS)
    )
    verb_ratio = verb_starts / max(1, len(bullet_lines))
    if verb_ratio < 0.3:
        penalty += 0.10
        suggestions.append(
            "Start more bullet points with strong action verbs "
            "(e.g. *Led*, *Built*, *Increased*)."
        )

    # Passive voice.
    passive_hits = len(PASSIVE_RE.findall(resume))
    if passive_hits > 3:
        penalty += 0.06
        suggestions.append(
            "Reduce passive voice — rewrite sentences so *you* are the actor."
        )

    # Non-quantified achievements.
    quantified = len(NUMBER_RE.findall(resume))
    if quantified < 3:
        penalty += 0.08
        suggestions.append(
            "Quantify achievements with numbers (%, ₹, time saved, scale)."
        )

    return min(penalty, 0.25), suggestions


def score_resume(resume_text: str, jd_text: str) -> AtsResult:
    """Compute an ATS compatibility score for a resume against a JD."""
    jd_keywords = extract_jd_keywords(jd_text)
    resume_terms = set(_content_terms(_tokens(resume_text)))

    matched, missing = [], []
    for kw in jd_keywords:
        # A multi-word keyword matches if all its parts appear in the resume.
        parts = kw.split()
        if all(p in resume_terms for p in parts):
            matched.append(kw)
        else:
            missing.append(kw)

    overlap = len(matched) / max(1, len(jd_keywords))
    semantic = _semantic_similarity(resume_text, jd_text)
    penalty, suggestions = _quality_penalties(resume_text)

    # Weighted blend: keyword match is what ATS parsers key on; semantic
    # similarity rewards genuine relevance; penalties dock weak writing.
    raw = 0.55 * overlap + 0.45 * semantic
    score = max(0, min(100, round((raw - penalty) * 100)))

    if missing:
        preview = ", ".join(missing[:8])
        suggestions.insert(
            0, f"Add or surface these JD keywords: *{preview}*."
        )

    return AtsResult(
        score=score,
        keyword_overlap=round(overlap, 3),
        semantic_similarity=round(semantic, 3),
        matched_keywords=matched,
        missing_keywords=missing,
        suggestions=suggestions,
    )

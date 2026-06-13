"""Tests for the ATS scoring engine (no network / API needed)."""

from bot.services import ats


JD = """
We are hiring a Backend Engineer. Required skills: Python, Django, PostgreSQL,
REST APIs, Docker, AWS. You will design scalable microservices, optimize
database queries, and build CI/CD pipelines. Experience with Kubernetes and
Redis is a plus.
"""

STRONG_RESUME = """
EXPERIENCE
- Built scalable Python microservices with Django and REST APIs serving 2M users
- Optimized PostgreSQL queries, reducing latency by 40%
- Containerized services with Docker and deployed on AWS using CI/CD pipelines
- Managed Redis caching layer and Kubernetes clusters
"""

WEAK_RESUME = """
EXPERIENCE
- Worked on some website stuff using a programming language
- Tasks were done and things were maintained by the team
- Responsible for various activities
"""


def test_extract_jd_keywords_finds_skills():
    keywords = ats.extract_jd_keywords(JD)
    joined = " ".join(keywords)
    assert "python" in joined
    assert "postgresql" in joined or "django" in joined


def test_strong_resume_scores_higher_than_weak():
    strong = ats.score_resume(STRONG_RESUME, JD)
    weak = ats.score_resume(WEAK_RESUME, JD)
    assert 0 <= weak.score <= 100
    assert 0 <= strong.score <= 100
    assert strong.score > weak.score


def test_weak_resume_gets_suggestions():
    weak = ats.score_resume(WEAK_RESUME, JD)
    assert weak.suggestions  # should recommend improvements
    assert weak.missing_keywords  # should be missing JD keywords


def test_matched_keywords_present_for_strong_resume():
    strong = ats.score_resume(STRONG_RESUME, JD)
    assert strong.matched_keywords
    assert strong.keyword_overlap > 0

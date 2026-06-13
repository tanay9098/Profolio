"""Round-trip tests: generate a PDF/DOCX, then parse it back to text."""

from pathlib import Path

from bot.services import parsing, pdf

SAMPLE = """JOHN DOE
Bengaluru, India | john@example.com

EXPERIENCE
- Led a team of 5 engineers to ship a payments platform
- Increased throughput by 35% by optimizing the database

SKILLS
- Python, Django, PostgreSQL, Docker
"""


def test_render_pdf_creates_file(tmp_path: Path):
    out = tmp_path / "resume.pdf"
    result = pdf.render_text_to_pdf(SAMPLE, out, doc_title="Resume")
    assert result.exists()
    assert result.stat().st_size > 0


def test_pdf_roundtrip_extracts_text(tmp_path: Path):
    out = tmp_path / "resume.pdf"
    pdf.render_text_to_pdf(SAMPLE, out, doc_title="Resume")
    text = parsing.extract_text(out)
    assert "EXPERIENCE" in text.upper()
    assert not parsing.looks_empty(text)


def test_docx_roundtrip(tmp_path: Path):
    from docx import Document

    doc = Document()
    for line in SAMPLE.splitlines():
        doc.add_paragraph(line)
    path = tmp_path / "resume.docx"
    doc.save(str(path))

    text = parsing.extract_text(path)
    assert "John Doe".lower() in text.lower()
    assert "Python" in text


def test_unsupported_file_raises(tmp_path: Path):
    bad = tmp_path / "resume.txt"
    bad.write_text("hello")
    try:
        parsing.extract_text(bad)
        assert False, "expected UnsupportedFileError"
    except parsing.UnsupportedFileError:
        pass

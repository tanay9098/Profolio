"""Temporary file helpers + retention cleanup (PRD §7.3).

Uploaded resumes and generated PDFs live under DATA_DIR and are deleted after
FILE_RETENTION_HOURS. The cleanup runs periodically via the bot's job queue.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from bot.config import settings

logger = logging.getLogger(__name__)


def user_dir(tg_user_hash: str) -> Path:
    d = settings.data_dir / tg_user_hash[:16]
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup_expired() -> int:
    """Delete files older than the retention window. Returns count removed."""
    cutoff = time.time() - settings.file_retention_hours * 3600
    removed = 0
    if not settings.data_dir.exists():
        return 0
    for path in settings.data_dir.rglob("*"):
        if path.is_file():
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError as exc:  # noqa: PERF203
                logger.warning("Could not delete %s: %s", path, exc)
    if removed:
        logger.info("Retention cleanup removed %d expired file(s)", removed)
    return removed


def safe_unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:  # noqa: BLE001
        logger.warning("Could not delete %s: %s", path, exc)

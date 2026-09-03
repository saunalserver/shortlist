"""Retire shortlisted postings that are too old or whose page says the job is gone.

Two checks, both cheap and conservative:
- **Age**: posted more than ``posted_max_days`` ago (or, when the source gave no date, first seen more than
  ``fetched_max_days`` ago). Most postings close within a month; anything older is noise in the review queue.
- **Link**: fetch the posting page. 404/410, or one of the "no longer accepting applications" phrases the
  big boards use → expired. Anything ambiguous (403, timeouts, JS-only pages) is left alone and re-checked later.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import time
from typing import Any

import requests

from autojob import db as D
from autojob.scraper import HEADERS

logger = logging.getLogger("autojob")

TIMEOUT = 15
_MIN_GAP = 1.0
DEAD_PHRASES = (
    "no longer accepting applications", "this job is no longer available", "job is no longer available",
    "this job has expired", "job has expired", "posting has expired", "this posting has expired",
    "position has been filled", "this position has been filled", "job is no longer active", "job is closed",
    "this job has closed", "job posting has closed", "the job you are looking for is no longer open",
    "this listing has expired", "job not found", "position is no longer available", "not accepting applications",
    "this job posting is no longer available", "this job posting has expired", "this opportunity is no longer available",
    "cette offre n'est plus disponible", "job is no longer open", "this job is no longer open",
    "posting is no longer available", "this role has been filled", "this vacancy has closed",
)
_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)


def check_link(url: str) -> str | None:
    """Return a reason string when the page says the job is gone, else None (alive or unknown)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as e:
        logger.debug("link check failed for %s: %s", url, str(e)[:100])
        return None
    if resp.status_code in (404, 410):
        return f"HTTP {resp.status_code}"
    if resp.status_code >= 400:
        return None   # 403 / 429 / 5xx tell us nothing about the job
    text = _TAGS.sub(" ", resp.text[:400_000]).lower()
    text = re.sub(r"\s+", " ", text)
    for phrase in DEAD_PHRASES:
        if phrase in text:
            return f"page says '{phrase}'"
    return None


def expire(conn: sqlite3.Connection, *, posted_max_days: int = 30, fetched_max_days: int = 45,
           link_checks: int = 0, dry_run: bool = False) -> dict[str, Any]:
    """Run the age rule, then up to ``link_checks`` page checks. Returns counts and the affected ids."""
    by_age = D.stale_by_age(conn, posted_max_days, fetched_max_days)
    expired: list[tuple[int, str]] = list(by_age)
    for jid, reason in by_age:
        if not dry_run:
            D.mark_expired(conn, jid, reason)
    if not dry_run:
        conn.commit()
    checked = 0
    if link_checks > 0:
        last = 0.0
        for job in D.jobs_for_link_check(conn, link_checks):
            wait = _MIN_GAP - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.monotonic()
            reason = check_link(job["url"])
            checked += 1
            if not dry_run:
                D.update_job(conn, job["id"], link_checked_at=D.now_iso())
            if reason:
                expired.append((job["id"], reason))
                logger.info("expired %s at %s — %s", job.get("title"), job.get("company"), reason)
                if not dry_run:
                    D.mark_expired(conn, job["id"], reason)
            if not dry_run:
                conn.commit()
    logger.info("expiry: %d by age, %d by link check (%d links checked)%s", len(by_age), len(expired) - len(by_age),
                checked, " [dry run]" if dry_run else "")
    return {"by_age": len(by_age), "by_link": len(expired) - len(by_age), "checked": checked,
            "ids": [i for i, _ in expired], "reasons": expired}

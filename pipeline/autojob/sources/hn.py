"""HN "Who is hiring" — monthly thread via the Algolia API (no key, ~2 requests/month).

Comments list openings as pipe-separated lines ("Acme | Vancouver, BC | Ops Coordinator").
We keep lines naming Canada/BC or remote whose role matches ``title_keywords``;
seen_urls dedupes old threads, so repeat runs cost nothing.
"""
from __future__ import annotations

import logging

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.prefilter import CANADA_MARKERS, REMOTE_MARKERS
from autojob.settings import Settings
from autojob.sources.base import get_json, title_matches

NAME = "hn"
logger = logging.getLogger("autojob")
ALGOLIA = "https://hn.algolia.com/api/v1"


def _latest_hiring_story() -> dict | None:
    data = get_json(f"{ALGOLIA}/search_by_date", params={"tags": "story,author_whoishiring", "hitsPerPage": 10},
                    retries=1)
    for hit in data.get("hits", []):
        if (hit.get("title") or "").lower().startswith("ask hn: who is hiring"):
            return hit
    return None


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    keywords = list(cfg.get("title_keywords", []))
    story = _latest_hiring_story()
    if not story:
        logger.info("[hn] no 'Who is hiring' thread found")
        return []
    comments = get_json(f"{ALGOLIA}/search",
                        params={"tags": f"comment,story_{story['objectID']}", "hitsPerPage": 1000}, retries=1)
    out: list[RawJob] = []
    for c in comments.get("hits", []):
        for raw_line in (c.get("comment_text") or "").split("\n"):
            line = clean_html(raw_line)          # comments are HTML — strip tags before parsing pipes
            parts = [p.strip(" -–—") for p in line.split("|")]
            if len(parts) < 2:
                continue
            low = " " + line.lower() + " "
            if not (any(k in low for k in CANADA_MARKERS) or any(k in low for k in REMOTE_MARKERS)):
                continue
            company = parts[0]
            role_parts = [p for p in parts[1:] if title_matches(p, keywords)]
            if not role_parts or not company or len(company) > 60:
                continue
            title = min(role_parts, key=len).replace("\n", " ")[:120]
            out.append(RawJob(
                url=canonical_url(f"https://news.ycombinator.com/item?id={c['objectID']}"),
                title=title, company=company[:60], source=NAME,
                location="Remote" if "remote" in low else "",
                description=truncate(line), snippet=snippet_of(line),
                posted_at=(c.get("created_at") or "")[:10] or None,
            ))
    logger.info("[hn] %d jobs from thread %s (%s)", len(out), story["objectID"], (story.get("created_at") or "")[:10])
    return out

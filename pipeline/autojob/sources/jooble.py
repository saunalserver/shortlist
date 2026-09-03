"""Jooble — global aggregator. Free key with a lifetime request cap, so few queries."""
from __future__ import annotations

import logging

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import post_json

NAME = "jooble"
logger = logging.getLogger("autojob")


def fetch(settings: Settings) -> list[RawJob]:
    key = settings.secrets.jooble_api_key
    if not key:
        logger.info("[jooble] no API key, skipping")
        return []
    cfg = settings.source(NAME)
    out: list[RawJob] = []
    seen: set[str] = set()
    for term in settings.source_queries(NAME)[: int(cfg.get("max_queries", 6))]:
        try:
            data = post_json(
                f"https://jooble.org/api/{key}",
                json={"keywords": term, "location": cfg.get("location", "Vancouver, BC"),
                      "radius": str(cfg.get("radius_km", 50)), "page": 1},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[jooble] '%s' failed: %s", term, str(e)[:120])
            continue
        for j in data.get("jobs", []):
            url = canonical_url(j.get("link", ""))
            if not url or url in seen:
                continue
            seen.add(url)
            desc = clean_html(j.get("snippet") or j.get("description") or "")
            out.append(RawJob(
                url=url, title=j.get("title", ""), company=j.get("company", ""), source=NAME,
                location=j.get("location", ""), description=truncate(desc), snippet=snippet_of(desc),
                employment_type=j.get("type") or None, posted_at=(j.get("updated") or "")[:10] or None,
            ))
    logger.info("[jooble] %d jobs", len(out))
    return out

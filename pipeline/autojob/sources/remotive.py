"""Remotive — remote jobs worldwide (public API, no key)."""
from __future__ import annotations

import logging

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import get_json

NAME = "remotive"
logger = logging.getLogger("autojob")
URL = "https://remotive.com/api/remote-jobs"


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    out: list[RawJob] = []
    seen: set[str] = set()
    for term in settings.source_queries(NAME):
        try:
            data = get_json(URL, params={"search": term, "limit": int(cfg.get("limit_per_query", 20))})
        except Exception as e:  # noqa: BLE001
            logger.warning("[remotive] '%s' failed: %s", term, str(e)[:120])
            continue
        for j in data.get("jobs", []):
            url = canonical_url(j.get("url", ""))
            if not url or url in seen:
                continue
            seen.add(url)
            desc = clean_html(j.get("description", ""))
            out.append(RawJob(
                url=url, title=j.get("title", ""), company=j.get("company_name", ""), source=NAME,
                location=j.get("candidate_required_location", ""), description=truncate(desc), snippet=snippet_of(desc),
                employment_type=j.get("job_type") or None, posted_at=(j.get("publication_date") or "")[:10] or None,
                remote=True,
            ))
    logger.info("[remotive] %d jobs", len(out))
    return out

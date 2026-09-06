"""Amazon jobs — public JSON search (no key, full descriptions inline).

GET https://www.amazon.jobs/en/search.json?city=Vancouver&result_limit=100&sort=recent
Amazon Vancouver posts real ops/program/support roles; descriptions and basic
qualifications arrive in the list response, so zero scrape cost.
"""
from __future__ import annotations

import logging
from datetime import datetime

from autojob.models import RawJob
from autojob.normalize import canonical_url, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import get_json

NAME = "amazon"
logger = logging.getLogger("autojob")
SEARCH = "https://www.amazon.jobs/en/search.json"


def _date(text: str | None) -> str | None:
    """'September  4, 2026' (double spaces happen) → ISO date."""
    if not text:
        return None
    try:
        return datetime.strptime(" ".join(text.split()), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    limit = int(cfg.get("result_limit", 100))
    pages = int(cfg.get("pages", 2))
    # passes: [{city: …} | {country: …}] — 2026-09-08 "both": Vancouver + Canada-wide
    # (no remote flag in the API, verified — on-site non-Vancouver rows die in the prefilter).
    passes = cfg.get("passes") or [{"city": cfg.get("city", "Vancouver")}]
    out: list[RawJob] = []
    seen: set[str] = set()
    for p in passes:
        geo = {"city": p["city"]} if p.get("city") else {"country": p.get("country", "CAN")}
        for page in range(pages):
            try:
                data = get_json(SEARCH, params={**geo, "result_limit": limit,
                                                "sort": "recent", "offset": page * limit}, retries=1)
            except Exception as e:  # noqa: BLE001
                logger.warning("[amazon] %s page %d failed: %s", p, page + 1, str(e)[:120])
                break
            jobs = data.get("jobs") or []
            for j in jobs:
                jid = j.get("id")
                if not jid:
                    continue
                url = canonical_url(f"https://www.amazon.jobs/en/jobs/{jid}")
                if url in seen:
                    continue
                seen.add(url)
                desc = (j.get("description") or "") + "\n\nBasic qualifications:\n" + (j.get("basic_qualifications") or "")
                out.append(RawJob(
                    url=url,
                    title=j.get("title") or "", company=j.get("company_name") or "Amazon", source=NAME,
                    location=j.get("normalized_location") or j.get("city") or "",
                    description=truncate(desc), snippet=snippet_of(desc),
                    employment_type=j.get("job_type") or None, posted_at=_date(j.get("posted_date")),
                ))
            if len(jobs) < limit:
                break
    logger.info("[amazon] %d jobs", len(out))
    return out

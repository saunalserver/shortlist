"""Working Nomads — remote jobs via the Elasticsearch endpoint the site itself uses
(``POST /jobsapi/_search``, no key). The public ``/api/exposed_jobs/`` feed only holds ~50
jobs; the search index holds everything.

One request per run: a phrase match on the title for every master query, limited to the
last ``days`` days. Residency policy (owner, 2026-09-28): only remote jobs doable from
Vancouver — a row is kept when ``locations`` is empty or names Canada / North America / the
Americas / anywhere. "Europe", "EMEA" or a list of countries without Canada is an explicit
residency restriction and dies here. ``apply_url`` is the employer's ATS link; descriptions
are inline, so no scrape is needed.
"""
from __future__ import annotations

import logging
import re

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import post_json

NAME = "workingnomads"
logger = logging.getLogger("autojob")
URL = "https://www.workingnomads.com/jobsapi/_search"
HEADERS = {"User-Agent": "python-requests/2.32 autojob", "Content-Type": "application/json"}

# A ``locations`` entry matching this means someone living in Vancouver may apply
# ("USA, Canada", "North America", "Americas", "Anywhere"…). "Latin America" alone does not.
ELIGIBLE = re.compile(r"canada|north america|(?<!latin )americas|worldwide|anywhere|global", re.I)
POSITION_TYPES = {"ft": "full-time", "pt": "part-time", "fr": "freelance", "co": "contract"}


def build_query(queries: list[str], days: int, size: int) -> dict:
    return {
        "size": size,
        "sort": [{"pub_date": "desc"}],
        "query": {"bool": {
            "should": [{"match_phrase": {"title": q}} for q in queries],
            "minimum_should_match": 1,
            "filter": [{"range": {"pub_date": {"gte": f"now-{days}d"}}}],
        }},
    }


def open_to_canada(locations: list[str] | None) -> bool:
    """Empty locations count as "remote, unspecified" → kept (the scorer judges from the text)."""
    locs = [str(x).strip() for x in (locations or []) if str(x).strip()]
    return not locs or any(ELIGIBLE.search(x) for x in locs)


def to_raw(s: dict, skip_levels: set[str]) -> RawJob | None:
    url = canonical_url(s.get("apply_url") or (
        f"https://www.workingnomads.com/jobs/{s['slug']}" if s.get("slug") else ""))
    if not url or not s.get("title") or s.get("expired"):
        return None
    if (s.get("position_type") or "ft") != "ft":
        return None
    if (s.get("experience_level") or "").upper() in skip_levels:
        return None
    locations = s.get("locations") or []
    desc = clean_html(s.get("description") or "")
    where = ", ".join(str(x) for x in locations[:8]) + (", …" if len(locations) > 8 else "")
    return RawJob(
        url=url, title=s["title"], company=s.get("company") or "", source=NAME,
        location=f"Remote — {where}" if where else "Remote",
        description=truncate(desc), snippet=snippet_of(desc),
        employment_type=POSITION_TYPES.get(s.get("position_type") or "ft", "full-time"), remote=True,
        posted_at=(s.get("pub_date") or "")[:10] or None,
        extra={"experience_level": s.get("experience_level"), "category": s.get("category_name")},
    )


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    skip_levels = {s.upper() for s in cfg.get("skip_experience_levels", []) or []}
    body = build_query(settings.source_queries(NAME), int(cfg.get("days", 7)), int(cfg.get("size", 300)))
    try:
        data = post_json(URL, json=body, headers=HEADERS)
    except Exception as e:  # noqa: BLE001
        logger.warning("[workingnomads] search failed: %s", str(e)[:160])
        return []
    hits = (data.get("hits") or {}).get("hits") or []
    out: list[RawJob] = []
    seen: set[str] = set()
    residency = other = 0
    for h in hits:
        src = h.get("_source") or {}
        if not open_to_canada(src.get("locations")):
            residency += 1
            continue
        job = to_raw(src, skip_levels)
        if job is None:
            other += 1
            continue
        if job.url in seen:
            continue
        seen.add(job.url)
        out.append(job)
    logger.info("[workingnomads] %d jobs of %d hits (%d dropped: residency outside Canada/NA/anywhere; "
                "%d: senior/not full-time/expired)", len(out), len(hits), residency, other)
    return out

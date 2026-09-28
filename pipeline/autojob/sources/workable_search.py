"""Workable's cross-company job search (jobs.workable.com, public JSON, no key).

The company-board source only reads Workable boards we already know by slug; this
endpoint searches every employer on Workable — the dominant ATS for European SMEs and
common with Canadian ones. One pass per ``passes`` entry (location + optional
``workplace``); full descriptions come inline, so no scraping is needed.

Quirks (verified 2026-09-28): ``sort`` is ignored but ``day_range`` works; pagination is
``nextPageToken`` → ``pageToken``; ``location=Europe`` also returns UAE/Georgia/etc., so
European passes keep only ``EUROPE`` countries; one role is often cloned per country, so
rows are deduped on company+title too.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import get_json, title_matches

NAME = "workable_search"
logger = logging.getLogger("autojob")
URL = "https://jobs.workable.com/api/v1/jobs"

EUROPE = {
    "france", "united kingdom", "ireland", "germany", "spain", "portugal", "italy", "netherlands", "belgium",
    "luxembourg", "switzerland", "austria", "denmark", "sweden", "norway", "finland", "iceland", "poland",
    "czechia", "czech republic", "slovakia", "hungary", "romania", "bulgaria", "greece", "cyprus", "malta",
    "croatia", "slovenia", "estonia", "latvia", "lithuania", "serbia", "bosnia and herzegovina", "montenegro",
    "north macedonia", "albania", "moldova", "ukraine",
}
FULL_TIME = {"", "full-time", "full time", "fulltime"}


OPEN_RESIDENCE = ("telecommute", "anywhere", "worldwide", "canada", "north america", "americas")


def residence_allows_us(locations: list[str]) -> bool:
    """Workable's ``locations`` list: remote rows normally carry "TELECOMMUTE" (= remote, no explicit
    residency rule). Only a list of specific places with no open/Canadian entry counts as a restriction."""
    if not locations:
        return True
    return any(k in str(loc).lower() for loc in locations for k in OPEN_RESIDENCE)


def _passes(cfg: dict) -> list[dict]:
    return list(cfg.get("passes") or [{"location": "Vancouver"}])


def parse_job(j: dict[str, Any], pc: dict[str, Any]) -> tuple[RawJob | None, str | None]:
    """One API row → RawJob for pass ``pc``, or (None, reason) when the pass rules drop it."""
    loc = j.get("location") or {}
    country = (loc.get("countryName") or "").strip()
    city = (loc.get("city") or "").strip()
    workplace = (j.get("workplace") or "").lower()          # remote | hybrid | on_site
    if pc.get("workplace") == "remote" and workplace != "remote":
        return None, "not remote"
    if pc.get("europe_only") and country.lower() not in EUROPE:
        return None, "outside Europe"
    if pc.get("country") and country.lower() != str(pc["country"]).lower():
        return None, "wrong country"
    emp = (j.get("employmentType") or "").strip().lower()
    if emp not in FULL_TIME:
        return None, "employment type"
    if workplace == "remote" and not residence_allows_us(j.get("locations") or []):
        return None, "residence restricted"
    url = canonical_url(j.get("url") or "")
    if not url:
        return None, "no url"

    place = ", ".join(p for p in (city, loc.get("subregion") or "", country) if p)
    if workplace == "remote":
        # countryName is the employer/office location, not a residency rule — "Remote (office: …)"
        # keeps that visible; the scorer reads any residency wording in the description.
        location = f"Remote (office: {', '.join(p for p in (city, country) if p)})" if (city or country) else "Remote"
    else:
        location = place + (" (hybrid)" if workplace == "hybrid" else "")
    desc = clean_html((j.get("description") or "") + "\n" + (j.get("requirementsSection") or ""))
    company = (j.get("company") or {}).get("title") or ""
    return RawJob(
        url=url, title=(j.get("title") or "").strip(), company=company, source=NAME, location=location,
        description=truncate(desc), snippet=snippet_of(desc), employment_type=j.get("employmentType") or None,
        posted_at=(j.get("created") or "")[:10] or None, remote=workplace == "remote",
        extra={"workplace": workplace, "company_website": (j.get("company") or {}).get("website")},
    ), None


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    keywords = list(cfg.get("title_keywords") or [])
    max_pages = int(cfg.get("max_pages", 3))
    pause = float(cfg.get("pause_s", 0.8))
    out: list[RawJob] = []
    seen: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()
    for pc in _passes(cfg):
        pc = {**cfg, **pc}
        n_pass = dropped = 0
        for q in settings.source_queries(NAME)[: int(pc.get("max_queries", 16))]:
            token: str | None = None
            for _ in range(max_pages):
                params = {"query": q, "location": pc["location"], "day_range": int(pc.get("day_range", 7))}
                if pc.get("workplace"):
                    params["workplace"] = pc["workplace"]
                if token:
                    params["pageToken"] = token
                try:
                    data = get_json(URL, params=params)
                except Exception as e:  # noqa: BLE001
                    logger.warning("[workable_search] %s/%s failed: %s", pc["location"], q, str(e)[:120])
                    break
                for j in data.get("jobs") or []:
                    if keywords and not title_matches(j.get("title") or "", keywords):
                        dropped += 1
                        continue
                    job, _why = parse_job(j, pc)
                    if job is None:
                        dropped += 1
                        continue
                    key = (job.company.lower(), job.title.lower())
                    if job.url in seen or key in seen_keys:
                        continue
                    seen.add(job.url)
                    seen_keys.add(key)
                    out.append(job)
                    n_pass += 1
                token = data.get("nextPageToken")
                time.sleep(pause)
                if not token:
                    break
        logger.info("[workable_search] %s%s: %d jobs (%d dropped)", pc["location"],
                    f"/{pc['workplace']}" if pc.get("workplace") else "", n_pass, dropped)
    logger.info("[workable_search] %d jobs", len(out))
    return out

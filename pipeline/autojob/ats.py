"""Applicant-tracking-system (ATS) helpers shared by the company and YC sources.

Greenhouse, Lever and Ashby all expose public JSON boards keyed by a company slug.
``probe`` finds which one a slug uses (cached in SQLite, including negative results),
and each ``fetch_*`` returns normalized jobs for a board.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime

import requests

from autojob.db import get_ats_cache, set_ats_cache
from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.sources.base import get_json, session

logger = logging.getLogger("autojob")

GREENHOUSE_LIST = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
LEVER_LIST = "https://api.lever.co/v0/postings/{slug}?mode=json"
ASHBY_LIST = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"

CACHE_TTL_DAYS = 30
PROBE_TIMEOUT = 8


def is_fresh(cached: dict | None) -> bool:
    if not cached or not cached.get("last_probed"):
        return False
    try:
        age = datetime.now(UTC) - datetime.fromisoformat(cached["last_probed"])
    except ValueError:
        return False
    return age.days < CACHE_TTL_DAYS


def probe(conn: sqlite3.Connection, slug: str, name: str) -> tuple[str | None, str | None]:
    """Return (ats_type, base_url) for a slug, using the cache when fresh. 'none' results are cached too."""
    cached = get_ats_cache(conn, slug)
    if is_fresh(cached):
        t = cached["ats_type"]
        return (None, None) if t in (None, "none", "unknown") else (t, cached["ats_base_url"])
    for ats_type, template in (("greenhouse", GREENHOUSE_LIST), ("lever", LEVER_LIST), ("ashbyhq", ASHBY_LIST)):
        url = template.format(slug=slug)
        try:
            resp = session().get(url, timeout=PROBE_TIMEOUT)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue
        ok = (ats_type == "greenhouse" and isinstance(data, dict) and "jobs" in data) or \
             (ats_type == "lever" and isinstance(data, list)) or \
             (ats_type == "ashbyhq" and isinstance(data, dict) and "jobs" in data)
        if ok:
            set_ats_cache(conn, slug, name, ats_type, url)
            conn.commit()
            return ats_type, url
    set_ats_cache(conn, slug, name, "none", "")
    conn.commit()
    return None, None


# ---------------------------------------------------------------------------
# Board fetchers — each returns *all* postings; callers filter by title/location.
# ---------------------------------------------------------------------------

def fetch_greenhouse(slug: str, company: str, source: str) -> list[RawJob]:
    data = get_json(GREENHOUSE_LIST.format(slug=slug), retries=1)
    out: list[RawJob] = []
    for j in data.get("jobs", []):
        desc = clean_html(j.get("content", ""))
        offices = ", ".join(o.get("name", "") for o in j.get("offices", []) if o.get("name"))
        loc = (j.get("location") or {}).get("name", "") or offices
        out.append(RawJob(
            url=canonical_url(j.get("absolute_url", "")), title=j.get("title", ""), company=company or slug.title(),
            source=source, location=loc, description=truncate(desc), snippet=snippet_of(desc),
            posted_at=(j.get("updated_at") or "")[:10] or None, remote=True if "remote" in loc.lower() else None,
            extra={"ats": "greenhouse", "slug": slug},
        ))
    return out


def fetch_lever(slug: str, company: str, source: str) -> list[RawJob]:
    data = get_json(LEVER_LIST.format(slug=slug), retries=1)
    out: list[RawJob] = []
    for p in data if isinstance(data, list) else []:
        cats = p.get("categories") or {}
        desc = p.get("descriptionPlain") or clean_html(p.get("description", ""))
        for lst in p.get("lists", []) or []:
            desc += f"\n{lst.get('text', '')}\n" + clean_html(lst.get("content", ""))
        loc = cats.get("location", "") or ", ".join(cats.get("allLocations", []) or [])
        wp = (p.get("workplaceType") or "").lower()
        out.append(RawJob(
            url=canonical_url(p.get("hostedUrl", "")), title=p.get("text", ""), company=company or slug.title(),
            source=source, location=loc, description=truncate(desc.strip()), snippet=snippet_of(desc),
            employment_type=cats.get("commitment"), remote=True if wp == "remote" or "remote" in loc.lower() else None,
            posted_at=_ms_to_date(p.get("createdAt")), extra={"ats": "lever", "slug": slug},
        ))
    return out


def fetch_ashby(slug: str, company: str, source: str) -> list[RawJob]:
    data = get_json(ASHBY_LIST.format(slug=slug), retries=1)
    out: list[RawJob] = []
    for j in data.get("jobs", []):
        if not j.get("isListed", True):
            continue
        desc = j.get("descriptionPlain") or clean_html(j.get("descriptionHtml", ""))
        loc = j.get("location", "") or ""
        secondary = [s.get("location", "") for s in j.get("secondaryLocations", []) or []]
        if secondary:
            loc = ", ".join([loc, *secondary]).strip(", ")
        comp = j.get("compensation") or {}
        summary = (comp.get("compensationTierSummary") or "")
        out.append(RawJob(
            url=canonical_url(j.get("jobUrl") or j.get("applyUrl") or ""), title=j.get("title", ""),
            company=company or slug.title(), source=source, location=loc, description=truncate(desc),
            snippet=snippet_of(desc), employment_type=j.get("employmentType"),
            remote=bool(j.get("isRemote")) if j.get("isRemote") is not None else None,
            posted_at=(j.get("publishedAt") or "")[:10] or None,
            extra={"ats": "ashbyhq", "slug": slug, "compensation": summary},
        ))
    return out


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashbyhq": fetch_ashby, "ashby": fetch_ashby}


def fetch_board(ats_type: str, slug: str, company: str, source: str) -> list[RawJob]:
    return FETCHERS[ats_type](slug, company, source)


def _ms_to_date(v) -> str | None:
    try:
        return datetime.fromtimestamp(int(v) / 1000, UTC).strftime("%Y-%m-%d") if v else None
    except (TypeError, ValueError, OverflowError):
        return None

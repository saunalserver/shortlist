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
from autojob.sources.base import get_json, get_text, session

logger = logging.getLogger("autojob")

GREENHOUSE_LIST = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
LEVER_LIST = "https://api.lever.co/v0/postings/{slug}?mode=json"
ASHBY_LIST = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
SMARTRECRUITERS_LIST = "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"
RECRUITEE_LIST = "https://{slug}.recruitee.com/api/offers/"
WORKABLE_LIST = "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"
PERSONIO_LIST = "https://{slug}.jobs.personio.com/xml"

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
    for ats_type, url in (("greenhouse", GREENHOUSE_LIST.format(slug=slug)), ("lever", LEVER_LIST.format(slug=slug)),
                          ("ashbyhq", ASHBY_LIST.format(slug=slug)),
                          ("smartrecruiters", SMARTRECRUITERS_LIST.format(slug=slug) + "&limit=1"),
                          ("recruitee", RECRUITEE_LIST.format(slug=slug)), ("workable", WORKABLE_LIST.format(slug=slug)),
                          ("personio", PERSONIO_LIST.format(slug=slug))):
        try:
            resp = session().get(url, timeout=PROBE_TIMEOUT)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        text = resp.text[:200]
        try:
            data = resp.json()
        except ValueError:
            data = None
        if ats_type == "personio":
            if text.lstrip().startswith("<?xml"):
                set_ats_cache(conn, slug, name, "personio", url)
                conn.commit()
                return "personio", url
            continue
        if data is None:
            continue
        ok = (ats_type == "greenhouse" and isinstance(data, dict) and "jobs" in data) or \
             (ats_type == "lever" and isinstance(data, list)) or \
             (ats_type == "ashbyhq" and isinstance(data, dict) and "jobs" in data) or \
             (ats_type == "smartrecruiters" and isinstance(data, dict) and data.get("totalFound")) or \
             (ats_type == "recruitee" and isinstance(data, dict) and "offers" in data) or \
             (ats_type == "workable" and isinstance(data, dict) and "jobs" in data)
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


def fetch_smartrecruiters(slug: str, company: str, source: str) -> list[RawJob]:
    """List has no descriptions (that costs one request per job) — titles + locations are enough
    for the prefilter; scoring runs on title/snippet like eluta does."""
    out: list[RawJob] = []
    for offset in range(0, 300, 100):
        data = get_json(SMARTRECRUITERS_LIST.format(slug=slug) + f"&offset={offset}", retries=1)
        content = data.get("content") or []
        for j in content:
            loc = j.get("location") or {}
            loc_str = ", ".join(v for v in (loc.get("city"), loc.get("region"), loc.get("country")) if v)
            out.append(RawJob(
                url=canonical_url(f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}"),
                title=j.get("name") or "", company=company or (j.get("company") or {}).get("name") or slug.title(),
                source=source, location=loc_str, posted_at=(j.get("releasedDate") or "")[:10] or None,
                remote=True if loc.get("remote") else None,
                employment_type=(j.get("typeOfEmployment") or {}).get("label"),
                extra={"ats": "smartrecruiters", "slug": slug},
            ))
        if len(content) < 100:
            break
    return out


def fetch_recruitee(slug: str, company: str, source: str) -> list[RawJob]:
    data = get_json(RECRUITEE_LIST.format(slug=slug), retries=1)
    out: list[RawJob] = []
    for o in data.get("offers", []):
        desc = clean_html(o.get("description") or "")
        out.append(RawJob(
            url=canonical_url(o.get("url") or f"https://{slug}.recruitee.com/o/{o.get('id')}"),
            title=o.get("title") or "", company=company or slug.title(), source=source,
            location="Remote" if o.get("remote") else ", ".join(v for v in (o.get("city"), o.get("country")) if v),
            description=truncate(desc), snippet=snippet_of(desc), posted_at=(o.get("created_at") or "")[:10] or None,
            remote=True if o.get("remote") else None,
            employment_type=o.get("employment_type") or None, extra={"ats": "recruitee", "slug": slug},
        ))
    return out


def fetch_workable(slug: str, company: str, source: str) -> list[RawJob]:
    data = get_json(WORKABLE_LIST.format(slug=slug), retries=1)
    out: list[RawJob] = []
    for j in data.get("jobs", []):
        loc = j.get("location") or {}
        loc_str = ", ".join(v for v in (loc.get("city"), loc.get("country")) if v)
        desc = j.get("description") or j.get("shortdescription") or ""
        out.append(RawJob(
            url=canonical_url(j.get("url") or f"https://apply.workable.com/{slug}/j/{j.get('shortcode') or ''}"),
            title=j.get("title") or "", company=company or data.get("name") or slug.title(), source=source,
            location=loc_str, description=truncate(clean_html(desc)), snippet=snippet_of(desc),
            posted_at=(j.get("created_at") or j.get("published_on") or "")[:10] or None,
            remote=True if loc.get("remote") else None,
            employment_type=(j.get("type") or {}).get("employment"), extra={"ats": "workable", "slug": slug},
        ))
    return out


def fetch_personio(slug: str, company: str, source: str) -> list[RawJob]:
    import xml.etree.ElementTree as ET
    text = get_text(PERSONIO_LIST.format(slug=slug), timeout=15)
    out: list[RawJob] = []
    for job in ET.fromstring(text).iter("job"):
        g = lambda tag: (job.findtext(tag) or "").strip()  # noqa: E731
        jid = g("id")
        out.append(RawJob(
            url=canonical_url(f"https://{slug}.jobs.personio.com/view/{jid}"),
            title=g("name") or g("title"), company=company or slug.title(), source=source,
            location=g("location") or g("office") or "", description=truncate(g("description") or g("tasks") or ""),
            posted_at=g("created_at")[:10] or None, employment_type=g("employmentType") or None,
            extra={"ats": "personio", "slug": slug},
        ))
    return out


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashbyhq": fetch_ashby, "ashby": fetch_ashby,
          "smartrecruiters": fetch_smartrecruiters, "recruitee": fetch_recruitee,
          "workable": fetch_workable, "personio": fetch_personio}


def fetch_board(ats_type: str, slug: str, company: str, source: str) -> list[RawJob]:
    return FETCHERS[ats_type](slug, company, source)


def _ms_to_date(v) -> str | None:
    try:
        return datetime.fromtimestamp(int(v) / 1000, UTC).strftime("%Y-%m-%d") if v else None
    except (TypeError, ValueError, OverflowError):
        return None

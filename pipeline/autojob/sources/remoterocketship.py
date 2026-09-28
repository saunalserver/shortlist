"""Remote Rocketship — remote jobs by title × region, parsed from the page's embedded
``__NEXT_DATA__`` JSON (no API, no key).

Each ``/country/<region>/jobs/<title-slug>/`` page embeds the 20 newest openings for that
title; ``?page=2`` is ignored by the site, which is fine for a twice-daily poll (every slug
gets < 20 new jobs a week). ``url`` is the employer's own ATS link.

Residency policy (owner, 2026-09-28): only remote jobs doable from Vancouver. A row whose
``location`` / ``locationCountries`` names places is kept only when one of them is Canada,
North America, the Americas or worldwide — "Bulgaria" or "Europe" alone is an explicit
residency restriction and dies here. Rows with no location info are kept.

Some ``canada/jobs/<slug>`` pages lose the title filter and serve the generic 11k-job listing;
a page whose total exceeds ``max_page_total`` is skipped. Medium ToS risk (the site sells a
premium tier) — keep the page count small.
"""
from __future__ import annotations

import json
import logging
import re
import time

from autojob.models import RawJob
from autojob.normalize import canonical_url, snippet_of
from autojob.settings import Settings
from autojob.sources.base import get_text

NAME = "remoterocketship"
logger = logging.getLogger("autojob")
BASE = "https://www.remoterocketship.com/country"
# Any of these in the allowed-places list means someone living in Vancouver may apply.
ELIGIBLE = re.compile(r"canada|north america|americas|worldwide|anywhere|global", re.I)
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def _pages(cfg: dict) -> list[str]:
    pages = [f"{r}/jobs/{s}" for r in cfg.get("regions", ["europe"]) or [] for s in cfg.get("title_slugs", []) or []]
    return pages + list(cfg.get("extra_pages", []) or [])


def parse_page(html: str) -> tuple[list[dict], int | None]:
    """The openings embedded in one title page and the page's total count ([] when no job data)."""
    m = _NEXT_DATA.search(html or "")
    if not m:
        return [], None
    try:
        props = json.loads(m.group(1))["props"]["pageProps"]
    except (ValueError, KeyError, TypeError):
        return [], None
    return list(props.get("initialJobOpenings") or []), props.get("initialTotalJobCount")


def open_to_canada(j: dict) -> bool:
    """False when the row lists allowed places and none of them covers Vancouver."""
    places = [str(p) for p in [j.get("location"), *(j.get("locationCountries") or [])] if p]
    return not places or any(ELIGIBLE.search(p) for p in places)


def _too_senior(j: dict) -> bool:
    senior = j.get("isSenior") or j.get("isLead")
    return bool(senior) and not (j.get("isEntryLevel") or j.get("isJunior") or j.get("isMidLevel"))


def _location(j: dict) -> str:
    countries = [str(c) for c in (j.get("locationCountries") or []) if c]
    where = j.get("location") or (", ".join(countries[:6]) if countries else "")
    if countries and len(countries) > 1:
        where = f"{where} ({', '.join(countries[:8])}{', …' if len(countries) > 8 else ''})"
    return f"Remote — {where}" if where else "Remote"


def to_raw(j: dict) -> RawJob | None:
    """One opening → RawJob, or None when it is not a full-time, junior-to-mid remote role."""
    url = canonical_url(j.get("url") or "")
    if not url or not j.get("roleTitle"):
        return None
    if (j.get("locationType") or "remote").lower() != "remote":
        return None
    emp = (j.get("employmentType") or "").lower()
    if emp and emp != "full-time":
        return None
    if _too_senior(j) or j.get("dateDeleted"):
        return None
    summary = j.get("twoLineJobDescriptionSummary") or j.get("jobDescriptionSummary") or ""
    company = j.get("company") or {}
    return RawJob(
        url=url, title=j["roleTitle"], company=company.get("name", "") if isinstance(company, dict) else "",
        source=NAME, location=_location(j), description="", snippet=snippet_of(summary),
        employment_type=j.get("employmentType"), remote=True,
        posted_at=(j.get("created_at") or "")[:10] or None,
        extra={"rr_slug": j.get("slug"), "ghost_score": j.get("ghostScore")},
    )


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    delay = float(cfg.get("delay_s", 1.5))
    max_total = int(cfg.get("max_page_total", 3000))
    out: list[RawJob] = []
    seen: set[str] = set()
    dropped = residency = 0
    for i, page in enumerate(_pages(cfg)):
        if i:
            time.sleep(delay)
        try:
            html = get_text(f"{BASE}/{page}/")
        except Exception as e:  # noqa: BLE001
            logger.warning("[remoterocketship] %s failed: %s", page, str(e)[:120])
            continue
        openings, total = parse_page(html)
        if not openings:
            logger.warning("[remoterocketship] %s: no job data in page", page)
        elif total and total > max_total:
            logger.warning("[remoterocketship] %s: %d jobs — title filter lost, page skipped", page, total)
            continue
        for j in openings:
            if not open_to_canada(j):
                residency += 1
                continue
            job = to_raw(j)
            if job is None:
                dropped += 1
                continue
            if job.url in seen:
                continue
            seen.add(job.url)
            out.append(job)
    logger.info("[remoterocketship] %d jobs (%d dropped: residency outside Canada/NA/worldwide; "
                "%d: senior/not full-time/not remote)", len(out), residency, dropped)
    return out

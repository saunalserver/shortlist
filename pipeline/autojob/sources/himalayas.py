"""Himalayas — remote jobs with country filters (public API, no key)."""
from __future__ import annotations

import logging
import time

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import get_json

NAME = "himalayas"
logger = logging.getLogger("autojob")
URL = "https://himalayas.app/jobs/api/search"
# Himalayas returns 403 to browser-like User-Agents but accepts plain client UAs.
HEADERS = {"User-Agent": "python-requests/2.32 autojob", "Accept": "application/json"}


def _query_defs(settings: Settings) -> list[dict]:
    cfg = settings.source(NAME)
    defs: list[dict] = []
    for q in settings.source_queries(NAME):
        for country in cfg.get("countries", []) or []:
            defs.append({"q": q, "country": country})
        if cfg.get("worldwide"):
            defs.append({"q": q, "worldwide": "true"})
    return defs


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    per_page = int(cfg.get("results_per_page", 20))
    skip_seniority = {s.lower() for s in cfg.get("skip_seniority", []) or []}
    out: list[RawJob] = []
    seen: set[str] = set()
    dropped = 0
    for qd in _query_defs(settings):
        for page in range(1, int(cfg.get("pages_per_query", 2)) + 1):
            params = {**qd, "limit": per_page, "page": page}
            try:
                data = get_json(URL, params=params, headers=HEADERS)
            except Exception as e:  # noqa: BLE001
                logger.warning("[himalayas] %s p%d failed: %s", qd.get("q"), page, str(e)[:120])
                break
            jobs = data if isinstance(data, list) else data.get("jobs", [])
            for j in jobs:
                url = canonical_url(j.get("applicationLink") or j.get("guid") or "")
                if not url or url in seen:
                    continue
                seen.add(url)
                seniority = {str(s).lower() for s in (j.get("seniority") or [])}
                if seniority & skip_seniority:
                    dropped += 1
                    continue
                desc = clean_html(j.get("description", ""))
                out.append(RawJob(
                    url=url, title=j.get("title", ""), company=j.get("companyName", ""), source=NAME,
                    location=", ".join(j.get("locationRestrictions", []) or []) or "Remote",
                    description=truncate(desc), snippet=snippet_of(j.get("excerpt") or desc),
                    salary_min=j.get("minSalary"), salary_max=j.get("maxSalary"), salary_currency=j.get("currency"),
                    employment_type=j.get("employmentType"), remote=True,
                    posted_at=_epoch_to_date(j.get("pubDate")),
                    extra={"company_slug": j.get("companySlug"), "seniority": j.get("seniority")},
                ))
            if len(jobs) < per_page:
                break
            time.sleep(0.4)
    logger.info("[himalayas] %d jobs (%d dropped by seniority label)", len(out), dropped)
    return out


def _epoch_to_date(v) -> str | None:
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(int(v))) if v else None
    except (TypeError, ValueError, OverflowError):
        return None

"""Workday job boards (UBC, Aritzia, STEMCELL…) via the public ``wday/cxs`` API — no key.

Search: POST https://<tenant>.<wd>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs
        {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "…"}
Detail: GET  https://<tenant>.<wd>.myworkdayjobs.com/wday/cxs/<tenant>/<site><externalPath>
Search results carry title, location and a relative posting date only; the description costs one
more request per job, so it is fetched only for postings that pass the title/location filter and
are not already in the database, up to ``max_details_per_run``.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime, timedelta

from autojob.db import connect
from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.prefilter import location_reason
from autojob.settings import Settings
from autojob.sources.base import session, title_matches

NAME = "workday"
logger = logging.getLogger("autojob")
PAGE = 20
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


def _base(t: dict) -> str:
    return f"https://{t['tenant']}.{t.get('wd', 'wd3')}.myworkdayjobs.com"


def posted_on_to_date(text: str | None, today: datetime | None = None) -> str | None:
    """'Posted Today' / 'Posted Yesterday' / 'Posted 8 Days Ago' / 'Posted 30+ Days Ago' → ISO date."""
    if not text:
        return None
    now = today or datetime.now(UTC)
    t = text.lower()
    if "today" in t:
        return now.strftime("%Y-%m-%d")
    if "yesterday" in t:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\+?\s*days?", t)
    if m:
        return (now - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
    return None


def _search(t: dict, text: str, offset: int) -> dict:
    url = f"{_base(t)}/wday/cxs/{t['tenant']}/{t['site']}/jobs"
    resp = session().post(url, json={"appliedFacets": {}, "limit": PAGE, "offset": offset, "searchText": text},
                          headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _detail(t: dict, external_path: str) -> dict:
    url = f"{_base(t)}/wday/cxs/{t['tenant']}/{t['site']}{external_path}"
    resp = session().get(url, headers={"Accept": "application/json"}, timeout=20)
    resp.raise_for_status()
    return resp.json().get("jobPostingInfo") or {}


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    tenants = [t for t in (cfg.get("tenants") or []) if t.get("tenant") and t.get("site")]
    queries = list(cfg.get("queries") or settings.queries)
    pages = int(cfg.get("pages_per_query", 2))
    keywords = list(cfg.get("title_keywords", []))
    detail_budget = int(cfg.get("max_details_per_run", 60))
    loc_cfg = settings.get("prefilter.location", {}) or {}
    out: list[RawJob] = []
    details = 0
    with connect() as conn:
        for t in tenants:
            found: dict[str, dict] = {}
            for q in queries:
                for page in range(pages):
                    try:
                        data = _search(t, q, page * PAGE)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("[workday] %s '%s' p%d failed: %s", t["tenant"], q, page + 1, str(e)[:120])
                        break
                    postings = data.get("jobPostings") or []
                    for p in postings:
                        path = p.get("externalPath")
                        if path and path not in found:
                            found[path] = p
                    if len(postings) < PAGE:
                        break
                    time.sleep(0.3)
            kept = 0
            for path, p in found.items():
                title = p.get("title") or ""
                loc = p.get("locationsText") or ""
                if keywords and not title_matches(title, keywords):
                    continue
                if location_reason(loc, loc_cfg, None):
                    continue
                url = canonical_url(f"{_base(t)}/{t['site']}{path}")
                job = RawJob(url=url, title=title, company=t.get("name") or t["tenant"].title(), source=NAME,
                             location=loc, posted_at=posted_on_to_date(p.get("postedOn")),
                             remote=True if "remote" in loc.lower() else None, extra={"tenant": t["tenant"]})
                already = conn.execute("SELECT 1 FROM seen_urls WHERE url = ?", (url,)).fetchone()
                if not already and details < detail_budget:
                    try:
                        info = _detail(t, path)
                        details += 1
                        desc = clean_html(info.get("jobDescription", ""))
                        job.description, job.snippet = truncate(desc), snippet_of(desc)
                        job.employment_type = info.get("timeType") or None
                        job.posted_at = (info.get("startDate") or "")[:10] or job.posted_at
                        time.sleep(0.3)
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[workday] detail failed for %s: %s", url, str(e)[:100])
                out.append(job)
                kept += 1
            logger.info("[workday] %s: %d postings searched, %d relevant", t["tenant"], len(found), kept)
    logger.info("[workday] %d jobs from %d tenants (%d descriptions fetched)", len(out), len(tenants), details)
    return out

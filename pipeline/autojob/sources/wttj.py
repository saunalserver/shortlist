"""Welcome to the Jungle (+ Otta, merged into it) via the public Algolia index the website uses.

The best French startup/scale-up board: CDI (``contract_type:full_time``), remote mode
(``remote`` ∈ fulltime/partial/punctual/no/unknown), minimum years of experience and office
country are all indexed. It also carries ~200 Canadian postings a week.

One request per (pass × query); results are filtered to ``title_keywords`` (English + French,
so "opérations" matches but "opérateur" does not). A query of ``*`` means "everything the pass
filters allow" — full-remote France is only ~130 postings/week, so one sweep beats many queries.
Summary + key missions + profile are enough text to score, so no scraping is needed.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import post_json, title_matches

NAME = "wttj"
logger = logging.getLogger("autojob")
# Public, search-only Algolia key shipped to every visitor by welcometothejungle.com (not a secret).
# If it rotates, re-read it from the site's JS bundle ("algolia" app id / api key).
ALGOLIA_APP_ID = "CSEKHVMS53"
ALGOLIA_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
URL = f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/wttj_jobs_production_fr/query"
HEADERS = {
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "X-Algolia-API-Key": ALGOLIA_API_KEY,
    "Referer": "https://www.welcometothejungle.com/",   # 403 without it
    "Content-Type": "application/json",
}
JOB_URL = "https://www.welcometothejungle.com/fr/companies/{org}/jobs/{slug}"
REMOTE_LABEL = {"fulltime": "remote", "partial": "hybrid", "punctual": "occasional remote"}


def _passes(cfg: dict) -> list[dict]:
    return list(cfg.get("passes") or [])


def _pick_office(offices: list[dict], pc: dict) -> dict:
    """The office this pass matched on: a listed city, else the pass's country, else the first."""
    cities = {c.lower() for c in pc.get("office_cities", []) or []}
    codes = {c.upper() for c in pc.get("country_codes", []) or []}
    for want in (lambda o: (o.get("city") or "").lower() in cities, lambda o: (o.get("country_code") or "") in codes):
        for o in offices:
            if want(o):
                return o
    return offices[0] if offices else {}


def parse_hit(h: dict[str, Any], pc: dict | None = None,
              max_experience: float | None = None) -> tuple[RawJob | None, str | None]:
    """One Algolia hit → RawJob for pass ``pc``, or (None, reason)."""
    if h.get("contract_type") and h["contract_type"] != "full_time":
        return None, "contract"
    exp = h.get("experience_level_minimum")
    if max_experience is not None and exp is not None and float(exp) > max_experience:
        return None, "experience"
    org = h.get("organization") or {}
    if not org.get("slug") or not h.get("slug"):
        return None, "no url"
    url = canonical_url(JOB_URL.format(org=org["slug"], slug=h["slug"]))

    o = _pick_office(h.get("offices") or [], pc or {})
    country, city = o.get("country") or "", o.get("city") or ""
    mode = (h.get("remote") or "").lower()
    remote = mode == "fulltime"
    if remote:
        # office country, not a residency rule — the scorer reads residency wording in the text
        location = f"Remote (office: {', '.join(p for p in (city, country) if p)})" if (city or country) else "Remote"
    else:
        location = ", ".join(p for p in (city, o.get("state") or "", country) if p)
        if mode in REMOTE_LABEL:
            location += f" ({REMOTE_LABEL[mode]})"

    missions = h.get("key_missions") or []
    parts = [h.get("summary") or "", "Missions:\n- " + "\n- ".join(missions) if missions else "", h.get("profile") or ""]
    desc = clean_html("\n\n".join(p for p in parts if p))
    salary_ok = (h.get("salary_period") or "yearly") == "yearly"
    return RawJob(
        url=url, title=(h.get("name") or "").strip(), company=org.get("name") or "", source=NAME,
        location=location, description=truncate(desc), snippet=snippet_of(h.get("summary") or desc),
        salary_min=h.get("salary_minimum") if salary_ok else None,
        salary_max=h.get("salary_maximum") if salary_ok else None,
        salary_currency=h.get("salary_currency") if salary_ok else None,
        employment_type="full_time", posted_at=(h.get("published_at") or "")[:10] or None, remote=remote,
        extra={"remote_mode": mode, "language": h.get("language"), "experience_min": exp},
    ), None


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    keywords = list(cfg.get("title_keywords") or [])
    max_exp = cfg.get("max_experience_years")
    per_page = int(cfg.get("hits_per_page", 200))
    since = int(time.time()) - int(cfg.get("max_days_old", 7)) * 86400
    out: list[RawJob] = []
    seen: set[str] = set()
    for pc in _passes(cfg):
        n_pass = dropped = 0
        for q in settings.source_queries(NAME)[: int(cfg.get("max_queries", 12))]:
            for page in range(int(cfg.get("max_pages", 3))):
                body = {"query": "" if q == "*" else q, "hitsPerPage": per_page, "page": page,
                        "filters": pc["filters"], "numericFilters": [f"published_at_timestamp>{since}"]}
                try:
                    data = post_json(URL, json=body, headers=HEADERS)
                except Exception as e:  # noqa: BLE001
                    logger.warning("[wttj] %s/%s failed: %s", pc.get("name"), q, str(e)[:120])
                    break
                for h in data.get("hits") or []:
                    if keywords and not title_matches(h.get("name") or "", keywords):
                        dropped += 1
                        continue
                    job, _why = parse_hit(h, pc, float(max_exp) if max_exp is not None else None)
                    if job is None:
                        dropped += 1
                        continue
                    if job.url in seen:
                        continue
                    seen.add(job.url)
                    out.append(job)
                    n_pass += 1
                time.sleep(0.4)
                if page + 1 >= int(data.get("nbPages") or 0):
                    break
        logger.info("[wttj] %s: %d jobs (%d dropped)", pc.get("name"), n_pass, dropped)
    logger.info("[wttj] %d jobs", len(out))
    return out

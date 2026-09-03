"""Y Combinator companies marked "hiring" → detect their ATS → pull ops roles.

Cost control: ATS detection is cached 30 days (negative results too) and at most
``max_new_probes_per_run`` new companies are probed per run.
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlparse

from autojob import ats
from autojob.db import connect, get_ats_cache, set_ats_cache
from autojob.models import RawJob
from autojob.settings import Settings
from autojob.sources.ats_companies import location_ok
from autojob.sources.base import get_text, post_json, title_matches

NAME = "yc"
logger = logging.getLogger("autojob")
YC_COMPANIES_PAGE = "https://www.ycombinator.com/companies"
ALGOLIA_INDEX = "YCCompany_production"


def _algolia_credentials(html: str) -> tuple[str | None, str | None]:
    m = re.search(r'window\.AlgoliaOpts\s*=\s*\{\s*"app"\s*:\s*"([^"]+)"\s*,\s*"key"\s*:\s*"([^"]+)"', html)
    return (m.group(1), m.group(2)) if m else (None, None)


def _hiring_companies(app_id: str, api_key: str) -> list[dict]:
    host = f"https://{app_id}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
    headers = {"X-Algolia-Application-Id": app_id, "X-Algolia-API-Key": api_key}
    companies: list[dict] = []
    page = 0
    while True:
        body = {"params": f"facetFilters=%5B%22isHiring%3Atrue%22%5D&hitsPerPage=200&page={page}"}
        data = post_json(host, json=body, headers=headers)
        hits = data.get("hits", [])
        companies += [{"slug": h.get("slug", ""), "name": h.get("name", ""), "website": h.get("website", "")} for h in hits]
        page += 1
        if not hits or page >= int(data.get("nbPages", 1)):
            break
    return companies


def slug_from_domain(website: str | None) -> str:
    if not website:
        return ""
    host = (urlparse(website if "://" in website else f"https://{website}").hostname or "").removeprefix("www.")
    parts = host.split(".")
    multi = {"co.uk", "com.au", "co.nz", "co.jp", "co.in", "co.za", "com.br", "com.mx"}
    if len(parts) >= 3 and ".".join(parts[-2:]) in multi:
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")


def slug_from_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("'", "").replace(".", "")).strip("-")


def candidate_slugs(slug: str, name: str, website: str) -> list[str]:
    out = [slug]
    for c in (slug_from_domain(website), slug_from_name(name)):
        if c and c not in out:
            out.append(c)
    return out


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    keywords = list(cfg.get("title_keywords", []))
    budget = int(cfg.get("max_new_probes_per_run", 100))
    try:
        app_id, key = _algolia_credentials(get_text(YC_COMPANIES_PAGE))
        if not app_id:
            raise RuntimeError("Algolia credentials not found on YC page")
        companies = _hiring_companies(app_id, key)
    except Exception as e:  # noqa: BLE001
        logger.warning("[yc] discovery failed: %s", str(e)[:140])
        return []
    logger.info("[yc] %d hiring companies", len(companies))

    out: list[RawJob] = []
    probed_new = 0
    boards = 0
    with connect() as conn:
        for c in companies:
            slug, name, website = c["slug"], c["name"], c.get("website", "")
            if not slug:
                continue
            cached = get_ats_cache(conn, slug)
            if cached and ats.is_fresh(cached):
                if cached["ats_type"] in (None, "none", "unknown"):
                    continue
                ats_type, base = cached["ats_type"], cached["ats_base_url"]
            else:
                if probed_new >= budget:
                    continue
                probed_new += 1
                ats_type = base = None
                for cand in candidate_slugs(slug, name, website):
                    ats_type, base = ats.probe(conn, cand, name)
                    if ats_type:
                        break
                if not ats_type:
                    # remember the negative under the YC slug so alternates aren't re-probed daily
                    set_ats_cache(conn, slug, name, "none", "")
                    conn.commit()
            if not ats_type or not base:
                continue
            boards += 1
            ats_slug = base.split("/boards/")[-1].split("/")[0] if ats_type == "greenhouse" else \
                base.rstrip("/").split("/")[-1].split("?")[0]
            try:
                jobs = ats.fetch_board(ats_type, ats_slug, name, NAME)
            except Exception as e:  # noqa: BLE001
                logger.debug("[yc] %s board failed: %s", name, str(e)[:100])
                continue
            for j in jobs:
                if j.url and title_matches(j.title, keywords) and location_ok(settings, j.location, j.remote):
                    out.append(j)
            time.sleep(0.2)
    logger.info("[yc] %d ops jobs from %d boards (%d new companies probed)", len(out), boards, probed_new)
    return out

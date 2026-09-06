"""Adzuna — Canada-wide aggregator. Free API key (developer.adzuna.com)."""
from __future__ import annotations

import logging

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import get_json

NAME = "adzuna"
logger = logging.getLogger("autojob")
BASE = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def _wheres(cfg: dict) -> list[str]:
    """``where`` accepts one place or a list — a list runs one pass per place."""
    w = cfg.get("where", "Vancouver")
    return list(w) if isinstance(w, list) else [w]


def fetch(settings: Settings) -> list[RawJob]:
    s = settings.secrets
    if not (s.adzuna_app_id and s.adzuna_app_key):
        logger.info("[adzuna] no API key, skipping")
        return []
    cfg = settings.source(NAME)
    country = (settings.get("profile.country", "CA") or "CA").lower()
    out: list[RawJob] = []
    seen: set[str] = set()
    # "title": every query word must appear in the job title. "any": anywhere in the posting (Adzuna's default),
    # which matches "operations" in the body of every retail and warehouse ad in town.
    term_param = "title_only" if cfg.get("match", "title") == "title" else "what"
    for where in _wheres(cfg):
        # Distance is meaningless (and restricting) around a country-wide "canada" — requests drops the None param.
        distance = None if where.strip().lower() == country else cfg.get("distance_km", 50)
        for term in settings.source_queries(NAME):
            for page in range(1, int(cfg.get("pages", 2)) + 1):
                try:
                    data = get_json(
                        BASE.format(country=country, page=page),
                        params={
                            "app_id": s.adzuna_app_id, "app_key": s.adzuna_app_key, term_param: term,
                            "where": where, "distance": distance,
                            "results_per_page": cfg.get("results_per_page", 50), "max_days_old": cfg.get("max_days_old", 7),
                            "sort_by": "date", "content-type": "application/json",
                        },
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("[adzuna] '%s' page %d failed: %s", term, page, str(e)[:120])
                    break
                results = data.get("results", [])
                for j in results:
                    url = canonical_url(j.get("redirect_url", ""))
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    desc = clean_html(j.get("description", ""))
                    out.append(RawJob(
                        url=url, title=j.get("title", ""), company=(j.get("company") or {}).get("display_name", ""),
                        source=NAME, location=(j.get("location") or {}).get("display_name", ""),
                        description=truncate(desc), snippet=snippet_of(desc),
                        salary_min=j.get("salary_min"), salary_max=j.get("salary_max"), salary_currency="CAD",
                        employment_type=j.get("contract_time"), posted_at=(j.get("created") or "")[:10] or None,
                    ))
                if len(results) < int(cfg.get("results_per_page", 50)):
                    break
    logger.info("[adzuna] %d jobs", len(out))
    return out

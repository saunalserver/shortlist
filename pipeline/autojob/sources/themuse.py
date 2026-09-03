"""The Muse — public jobs API with category/level/location filters (no key)."""
from __future__ import annotations

import logging

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import get_json

NAME = "themuse"
logger = logging.getLogger("autojob")
URL = "https://www.themuse.com/api/public/jobs"


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    wanted_levels = {lv.lower() for lv in cfg.get("levels", [])}
    out: list[RawJob] = []
    seen: set[str] = set()
    for page in range(1, int(cfg.get("pages", 3)) + 1):
        params: list[tuple[str, str]] = [("page", str(page))]
        params += [("category", c) for c in cfg.get("categories", [])]
        params += [("location", loc) for loc in cfg.get("locations", [])]
        params += [("level", lv.title() if lv != "mid" else "Mid Level") for lv in cfg.get("levels", [])]
        try:
            data = get_json(URL, params=params)
        except Exception as e:  # noqa: BLE001
            logger.warning("[themuse] page %d failed: %s", page, str(e)[:120])
            break
        results = data.get("results", [])
        for j in results:
            levels = {lv.get("short_name", "").lower() for lv in j.get("levels", [])}
            if wanted_levels and levels and not (levels & wanted_levels):
                continue
            url = canonical_url((j.get("refs") or {}).get("landing_page", ""))
            if not url or url in seen:
                continue
            seen.add(url)
            desc = clean_html(j.get("contents", ""))
            locs = ", ".join(loc.get("name", "") for loc in j.get("locations", []))
            out.append(RawJob(
                url=url, title=j.get("name", ""), company=(j.get("company") or {}).get("name", ""), source=NAME,
                location=locs, description=truncate(desc), snippet=snippet_of(desc),
                posted_at=(j.get("publication_date") or "")[:10] or None,
                remote=True if "remote" in locs.lower() else None,
            ))
        if page >= int(data.get("page_count", 1)):
            break
    logger.info("[themuse] %d jobs", len(out))
    return out

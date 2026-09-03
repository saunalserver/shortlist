"""RemoteOK — one public JSON feed with all current listings (no key)."""
from __future__ import annotations

import logging

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import get_json

NAME = "remoteok"
logger = logging.getLogger("autojob")
URL = "https://remoteok.com/api"


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    wanted = {t.lower() for t in cfg.get("tags", [])}
    try:
        data = get_json(URL)
    except Exception as e:  # noqa: BLE001
        logger.warning("[remoteok] failed: %s", str(e)[:120])
        return []
    out: list[RawJob] = []
    for j in data[1:] if isinstance(data, list) else []:
        tags = {t.lower() for t in j.get("tags", [])}
        if wanted and not (tags & wanted):
            continue
        url = canonical_url(j.get("url", ""))
        if not url:
            continue
        desc = clean_html(j.get("description", ""))
        out.append(RawJob(
            url=url, title=j.get("position") or j.get("slug", "").replace("-", " ").title(),
            company=j.get("company", ""), source=NAME, location=j.get("location", "") or "Remote",
            description=truncate(desc), snippet=snippet_of(desc),
            salary_min=j.get("salary_min") or None, salary_max=j.get("salary_max") or None, salary_currency="USD",
            posted_at=(j.get("date") or "")[:10] or None, remote=True,
        ))
    logger.info("[remoteok] %d jobs", len(out))
    return out

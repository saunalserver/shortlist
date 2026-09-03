"""Jobicy — remote jobs with a geo filter (public API, no key)."""
from __future__ import annotations

import logging

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import get_json

NAME = "jobicy"
logger = logging.getLogger("autojob")
URL = "https://jobicy.com/api/v2/remote-jobs"


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    out: list[RawJob] = []
    seen: set[str] = set()
    tags = cfg.get("tags") or [None]
    for tag in tags:
        params = {"count": int(cfg.get("count", 50)), "geo": cfg.get("geo", "canada")}
        if tag:
            params["industry"] = tag
        try:
            data = get_json(URL, params=params)
        except Exception as e:  # noqa: BLE001
            logger.warning("[jobicy] tag %s failed: %s", tag, str(e)[:120])
            continue
        for j in data.get("jobs", []):
            url = canonical_url(j.get("url", ""))
            if not url or url in seen:
                continue
            seen.add(url)
            desc = clean_html(j.get("jobDescription", ""))
            out.append(RawJob(
                url=url, title=j.get("jobTitle", ""), company=j.get("companyName", ""), source=NAME,
                location=j.get("jobGeo", "") or "Remote", description=truncate(desc), snippet=snippet_of(j.get("jobExcerpt") or desc),
                salary_min=j.get("annualSalaryMin") or None, salary_max=j.get("annualSalaryMax") or None,
                salary_currency=j.get("salaryCurrency") or None,
                employment_type=", ".join(j.get("jobType", []) or []) or None,
                posted_at=(j.get("pubDate") or "")[:10] or None, remote=True,
                extra={"level": j.get("jobLevel")},
            ))
    logger.info("[jobicy] %d jobs", len(out))
    return out

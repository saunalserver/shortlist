"""Government of Canada Job Bank — HTML search results (no API)."""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from autojob.models import RawJob
from autojob.normalize import canonical_url
from autojob.settings import Settings
from autojob.sources.base import get_text

NAME = "jobbank"
logger = logging.getLogger("autojob")
SEARCH_URL = "https://www.jobbank.gc.ca/jobsearch/jobsearch"


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    out: list[RawJob] = []
    seen: set[str] = set()
    for term in settings.source_queries(NAME)[: int(cfg.get("max_queries", 8))]:
        try:
            html = get_text(SEARCH_URL, params={"searchstring": term, "locationstring": cfg.get("location", "Vancouver, BC"),
                                                 "sort": "D"})
        except Exception as e:  # noqa: BLE001
            logger.warning("[jobbank] '%s' failed: %s", term, str(e)[:120])
            continue
        soup = BeautifulSoup(html, "lxml")
        for article in soup.find_all("article"):
            link = article.select_one("a[href*='/jobposting/']")
            if not link:
                continue
            href = link.get("href", "")
            if href.startswith("/"):
                href = "https://www.jobbank.gc.ca" + href
            url = canonical_url(href.split(";")[0])
            if not url or url in seen:
                continue
            title_el = article.select_one("span.noctitle")
            title = title_el.get_text(strip=True) if title_el else ""
            if len(title) < 4:
                continue
            seen.add(url)
            company_el = article.select_one("li.business") or article.select_one(".business-name")
            loc_el = article.select_one("li.location")
            sal_el = article.select_one("li.salary")
            date_el = article.select_one("li.date")
            out.append(RawJob(
                url=url, title=title, company=company_el.get_text(strip=True) if company_el else "", source=NAME,
                location=loc_el.get_text(" ", strip=True).replace("Location", "").strip() if loc_el else "",
                snippet=sal_el.get_text(" ", strip=True).replace("Salary", "").strip() if sal_el else "",
                posted_at=date_el.get_text(strip=True) if date_el else None,
            ))
    logger.info("[jobbank] %d jobs", len(out))
    return out

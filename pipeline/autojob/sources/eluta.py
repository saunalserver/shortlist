"""Eluta.ca — Canadian job aggregator (Canada's Top 100 Employers), searched within a city radius. No key.

Search results are server-rendered HTML: one ``div.organic-job`` per posting with title, employer, location,
salary, a snippet and a relative "last seen" time. The job URL is Eluta's own ``/spl/…`` page (stable id),
which links on to the employer's posting.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime, timedelta

from bs4 import BeautifulSoup

from autojob.models import RawJob
from autojob.normalize import canonical_url, snippet_of
from autojob.settings import Settings
from autojob.sources.base import get_text

NAME = "eluta"
logger = logging.getLogger("autojob")
SEARCH_URL = "https://www.eluta.ca/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def ago_to_date(text: str | None, today: datetime | None = None) -> str | None:
    """'16 hours ago' / '3 days ago' / '2 weeks ago' → ISO date."""
    if not text:
        return None
    now = today or datetime.now(UTC)
    m = re.search(r"(\d+)\s*(minute|hour|day|week|month)", text.lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta = {"minute": timedelta(minutes=n), "hour": timedelta(hours=n), "day": timedelta(days=n),
             "week": timedelta(weeks=n), "month": timedelta(days=30 * n)}[unit]
    return (now - delta).strftime("%Y-%m-%d")


def parse_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []
    for div in soup.select("div.organic-job"):
        a = div.select_one("a.lk-job-title")
        rel = (div.get("data-url") or (a.get("data-url") if a else "") or "").split("?")[0]
        if not a or not rel:
            continue
        emp = div.select_one("a.lk-employer")
        loc = div.select_one("span.location")
        sal = div.select_one("span.position-salary")
        desc = div.select_one("span.description")
        seen = div.select_one("a.lastseen")
        rows.append({
            "url": f"https://www.eluta.ca/{rel.lstrip('/')}",
            "title": (a.get("title") or a.get_text(" ", strip=True)).strip(),
            "company": emp.get_text(" ", strip=True) if emp else "",
            "location": loc.get_text(" ", strip=True) if loc else "",
            "salary": sal.get_text(" ", strip=True) if sal else "",
            "snippet": desc.get_text(" ", strip=True) if desc else "",
            "ago": seen.get_text(" ", strip=True) if seen else "",
        })
    return rows


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    location = cfg.get("location", "Vancouver, BC")
    out: list[RawJob] = []
    seen: set[str] = set()
    for term in settings.source_queries(NAME)[: int(cfg.get("max_queries", 8))]:
        for page in range(1, int(cfg.get("pages", 2)) + 1):
            try:
                html = get_text(SEARCH_URL, params={"q": term, "l": location, "pg": page}, headers=HEADERS)
            except Exception as e:  # noqa: BLE001
                logger.warning("[eluta] '%s' p%d failed: %s", term, page, str(e)[:120])
                break
            rows = parse_results(html)
            for r in rows:
                url = canonical_url(r["url"])
                if not url or url in seen or len(r["title"]) < 4:
                    continue
                seen.add(url)
                snippet = r["snippet"]
                if r["salary"]:
                    snippet = f"Salary: {r['salary']}. {snippet}"
                out.append(RawJob(url=url, title=r["title"], company=r["company"], source=NAME, location=r["location"],
                                  snippet=snippet_of(snippet, 400), posted_at=ago_to_date(r["ago"]),
                                  remote=True if "remote" in r["location"].lower() else None))
            if len(rows) < 10:
                break
            time.sleep(0.6)
    logger.info("[eluta] %d jobs", len(out))
    return out

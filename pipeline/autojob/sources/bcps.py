"""BC Public Service — every open external posting in one HTML table (hrsmart ATS). No key.

One request returns all postings (~80): ministry, requisition id, title (prefixed with the pay
classification, e.g. "FO 21R - Financial Analyst"), union, work option (Hybrid / On-Site), location(s)
and the date opened. Kept: Lower Mainland postings (a multi-location posting naming one of our cities
counts) whose title matches ``title_keywords``. The posting page is public, so the pipeline's scraper
fetches the full description later.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from autojob.models import RawJob
from autojob.normalize import canonical_url
from autojob.settings import Settings
from autojob.sources.base import get_text, title_matches

NAME = "bcps"
logger = logging.getLogger("autojob")
BASE = "https://bcpublicservice.hua.hrsmart.com"
LIST_URL = BASE + "/hr/ats/JobSearch/viewAll/jobSearchPaginationExternal_pageSize:100/jobSearchPaginationExternal_page:{page}"

DEFAULT_LOCAL = ["vancouver", "burnaby", "richmond", "surrey", "coquitlam", "new westminster", "delta", "langley",
                 "port moody", "port coquitlam", "north vancouver", "west vancouver", "white rock", "maple ridge"]
# Pay-classification prefix before the first dash, all caps/digits: "FO 21R - ", "SPO-CP 24R HTR - ",
# "PARALGL 18 + 10% - ", "PS INT PRO - ". A prefix with lowercase letters is part of the title.
_CLASS_PREFIX = re.compile(r"^([A-Z0-9][A-Za-z0-9 .+%()/-]{0,28}?)\s+[-–]\s+")
# Noise the ministries append to titles: "- Amended", "– Closing date extended", "**Work Options amended**"
_STARRED = re.compile(r"\*\*[^*]*(?:\*\*|$)")
_TITLE_NOISE = re.compile(
    r"\s*(?:[-–:_]\s*)?(?:AMENDED\b.*|closing date extended.*|close date extended.*|additional vacancies added.*)$", re.I)
_POSTCODE = re.compile(r"\s*[A-Z]\d[A-Z]\s?\d[A-Z]\d\b")


def clean_title(raw: str) -> str:
    t = re.sub(r"\s+", " ", raw or "").strip()
    m = _CLASS_PREFIX.match(t)
    if m and not re.search(r"[a-z]", re.sub(r"\([^)]*\)", "", m.group(1))):  # "SPO 24R (Growth)" is a code
        t = t[m.end():]
    t = _STARRED.sub("", t)
    t = _TITLE_NOISE.sub("", t)
    return t.strip(" -–*:_")


def clean_location(raw: str) -> str:
    """'Burnaby, BC, CA V3J 1N3 Multiple Locations, BC, CA (Primary) Vancouver, BC, CA V6B 0N8'
    → 'Burnaby, BC; Vancouver, BC'."""
    text = _POSTCODE.sub("", re.sub(r"\s+", " ", raw or ""))
    places = []
    for m in re.finditer(r"([A-Z0-9][A-Za-z0-9 .'-]+?), BC, CA(?: \(Primary\))?", text):
        city = m.group(1).strip()
        if city.lower() == "multiple locations":
            continue
        place = f"{city}, BC"
        if place not in places:
            places.append(place)
    return "; ".join(places) or text.strip()


def _date(s: str) -> str | None:
    try:
        return datetime.strptime(s.strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("#jobSearchResultsGrid_table") or soup.find("table")
    rows: list[dict] = []
    if not table:
        return rows
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        a = tr.find("a", href=re.compile(r"/Posting/view/\d+"))
        if len(tds) < 7 or not a:
            continue
        cells = [td.get_text(" ", strip=True) for td in tds]
        rows.append({
            "url": BASE + a["href"],
            "raw_title": a.get_text(" ", strip=True),
            "title": clean_title(a.get_text(" ", strip=True)),
            "ministry": cells[0],
            "req_id": cells[1],
            "union": cells[3],
            "work_option": cells[4],
            "location": clean_location(cells[5]),
            "posted_at": _date(cells[6]),
        })
    return rows


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    keywords = list(cfg.get("title_keywords") or [])
    exclude = [w.lower() for w in cfg.get("title_exclude", []) or []]
    local = [c.lower() for c in cfg.get("local_cities") or DEFAULT_LOCAL]
    rows: list[dict] = []
    for page in range(1, int(cfg.get("max_pages", 3)) + 1):
        try:
            html = get_text(LIST_URL.format(page=page), timeout=30)
        except Exception as e:  # noqa: BLE001
            logger.warning("[bcps] page %d failed: %s", page, str(e)[:120])
            break
        batch = parse_rows(html)
        rows.extend(batch)
        if len(batch) < 100:
            break
    out: list[RawJob] = []
    for r in rows:
        low_title, low_raw, loc = r["title"].lower(), r["raw_title"].lower(), r["location"].lower()
        if not any(c in loc for c in local):
            continue
        if keywords and not title_matches(r["title"], keywords):
            continue
        if any(w in low_title or w in low_raw for w in exclude):
            continue
        work = r["work_option"] or "not stated"
        out.append(RawJob(
            url=canonical_url(r["url"]), title=r["title"], company=f"BC Public Service — {r['ministry']}",
            source=NAME, location=r["location"], posted_at=r["posted_at"],
            snippet=f"{r['ministry']} · {work} · union {r['union'] or 'n/a'} · req {r['req_id']}",
            remote=False,
            extra={"work_option": r["work_option"], "raw_title": r["raw_title"], "no_fingerprint": True},
        ))
    logger.info("[bcps] %d jobs (%d postings open)", len(out), len(rows))
    return out

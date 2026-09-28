"""SAP SuccessFactors career sites (ICBC, BCLC, FortisBC, TELUS…) via their public RSS feed — no key.

Feed: GET https://<host>/services/rss/job/?locale=en_US&keywords=(<kw>)
Each item carries the title with the location in a trailing parenthesis ("Business Analyst
(Burnaby, British Columbia, Canada)"), a pubDate and the full HTML description, so there are no
extra requests. A feed returns at most ~20 items per keyword and the keyword also matches the
location text, so national employers are swept with "vancouver" / "remote" keywords too.
Kept: title matches ``title_keywords`` and the location is the Vancouver area, or remote in Canada.
"""
from __future__ import annotations

import html
import logging
import re
import time
from email.utils import parsedate_to_datetime

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.prefilter import is_local
from autojob.settings import Settings
from autojob.sources.base import get_text, title_matches

NAME = "successfactors"
logger = logging.getLogger("autojob")
DEFAULT_KEYWORDS = ["operations", "coordinator", "analyst", "specialist", "vancouver", "remote"]
_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
# "Canada", or a province after a comma ("Remote within, BC, CA") — "San Jose, CA, US" must not match.
_CANADA = re.compile(r"\bcanada\b|,\s*(bc|on|ab|qc|mb|sk|ns|nb|nl|pe|british columbia|ontario|alberta|quebec|québec)\b",
                     re.I)


def _tag(item: str, name: str) -> str:
    m = re.search(rf"<{name}>(.*?)</{name}>", item, re.S)
    if not m:
        return ""
    v = m.group(1).strip()
    if v.startswith("<![CDATA[") and v.endswith("]]>"):
        v = v[9:-3]
    return html.unescape(v).strip()


def split_title(raw: str) -> tuple[str, str]:
    """'Project Manager I (Vancouver, British Columbia (BC), Canada, V6A 4K6)' → (title, location).
    The location is the LAST balanced parenthesis group; it can itself contain parentheses."""
    raw = (raw or "").strip()
    if not raw.endswith(")"):
        return raw, ""
    depth = 0
    for i in range(len(raw) - 1, -1, -1):
        if raw[i] == ")":
            depth += 1
        elif raw[i] == "(":
            depth -= 1
            if depth == 0:
                return raw[:i].strip(), raw[i + 1:-1].strip()
    return raw, ""


def _pub_date(text: str) -> str | None:
    try:
        return parsedate_to_datetime(text).strftime("%Y-%m-%d") if text else None
    except (TypeError, ValueError, IndexError):
        return None


def location_keep(location: str, title: str = "") -> tuple[bool, bool]:
    """(keep, remote). Vancouver area in any mode, or remote anywhere in Canada."""
    loc = f" {location.lower()} "
    remote = "remote" in loc or "remote" in title.lower() or "virtual" in loc
    if is_local(loc):
        return True, remote
    if remote and _CANADA.search(location):
        return True, True
    return False, remote


def parse_feed(xml: str) -> list[dict]:
    rows = []
    for item in _ITEM.findall(xml or ""):
        title, location = split_title(_tag(item, "title"))
        link = _tag(item, "link") or _tag(item, "guid")
        if not title or not link:
            continue
        rows.append({"title": title, "location": location, "url": link,
                     "posted_at": _pub_date(_tag(item, "pubDate")), "description": clean_html(_tag(item, "description"))})
    return rows


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    keywords = list(cfg.get("keywords") or DEFAULT_KEYWORDS)
    title_kw = list(cfg.get("title_keywords") or settings.source("workday").get("title_keywords") or [])
    out: list[RawJob] = []
    seen: set[str] = set()
    for t in cfg.get("tenants", []) or []:
        base = t["url"].rstrip("/")
        kept = off_title = off_loc = 0
        for kw in t.get("keywords") or keywords:
            try:
                xml = get_text(f"{base}/services/rss/job/", params={"locale": t.get("locale", "en_US"),
                                                                     "keywords": f"({kw})"})
            except Exception as e:  # noqa: BLE001
                logger.warning("[successfactors] %s '%s' failed: %s", t.get("name"), kw, str(e)[:120])
                continue
            for r in parse_feed(xml):
                url = canonical_url(r["url"].split("?")[0])   # ?feedId=null&utm_… — the path is the job
                if url in seen:
                    continue
                seen.add(url)
                if title_kw and not title_matches(r["title"], title_kw):
                    off_title += 1
                    continue
                keep, remote = location_keep(r["location"], r["title"])
                if not keep:
                    off_loc += 1
                    continue
                kept += 1
                out.append(RawJob(
                    url=url, title=r["title"], company=t.get("name", ""), source=NAME, location=r["location"],
                    description=truncate(r["description"]), snippet=snippet_of(r["description"]),
                    posted_at=r["posted_at"], remote=True if remote else None,
                ))
            time.sleep(float(cfg.get("delay_s", 0.5)))
        logger.info("[successfactors] %s: %d kept (%d off-title, %d off-location)",
                    t.get("name"), kept, off_title, off_loc)
    logger.info("[successfactors] %d jobs from %d tenants", len(out), len(cfg.get("tenants", []) or []))
    return out

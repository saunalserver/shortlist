"""Fetch a job page and extract the description when a source only gave us a snippet."""
from __future__ import annotations

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from autojob.normalize import clean_html, truncate

logger = logging.getLogger("autojob")

TIMEOUT = 15
_MIN_GAP = 1.2
_last = 0.0
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
# Bot-walled — not worth the request. (eluta.ca serves a "are you a human?" page to anything but a search.)
BLOCKED = ("indeed.com", "ziprecruiter.com", "wellfound.com", "glassdoor.", "eluta.ca")
# A page that is really a bot check / login wall — must never be stored as a job description.
_BOT_TELLS = ("are you a human", "unusual requests from you", "verify you are human", "verify that you are human",
              "enable javascript and cookies", "access denied", "captcha", "please log in to continue",
              "checking your browser", "attention required")

_SELECTORS = {
    "greenhouse": ["#content", ".job__description", ".job-description"],
    "lever": ["[data-qa='job-description']", ".section-wrapper", "div.posting"],
    "linkedin": [".description__text", ".show-more-less-html__markup"],
    "ashbyhq": ["._descriptionText_", "[class*='description']"],
    "jobbank": ["#job-details-container", ".job-posting-detail-requirements", "#tp_jobdescription"],
    "workable": ["[data-ui='job-description']", ".section--text"],
    "smartrecruiters": [".job-sections", "#st-jobDescription"],
    "generic": ["article", "main", "[role='main']", ".job-description", ".job-detail", ".posting-content",
                "#job-description", "#description", ".content", "#content"],
}
_LISTING_TELLS = ("open roles", "open positions", "view all jobs", "browse jobs", "filter by department")


def _board(url: str) -> str:
    u = url.lower()
    for k in ("greenhouse", "lever", "linkedin", "ashbyhq", "jobbank", "workable", "smartrecruiters"):
        if k in u:
            return k
    return "generic"


def _pace() -> None:
    global _last
    wait = _MIN_GAP - (time.monotonic() - _last)
    if wait > 0:
        time.sleep(wait)
    _last = time.monotonic()


def scrape(url: str) -> dict | None:
    """Return {"description": str, "title": str|None} or None when nothing usable was found."""
    low = url.lower()
    if any(b in low for b in BLOCKED):
        return None
    _pace()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.debug("scrape failed %s: %s", url, str(e)[:100])
        return None
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup.select("script, style, nav, footer, header, noscript, iframe, form"):
        tag.decompose()

    # JSON-LD JobPosting is the cleanest signal when present.
    text = _from_json_ld(resp.text)
    board = _board(url)
    if not text:
        for sel in _SELECTORS.get(board, []) + (_SELECTORS["generic"] if board != "generic" else []):
            try:
                el = soup.select_one(sel)
            except Exception:  # noqa: BLE001
                continue
            if el and len(el.get_text(strip=True)) > 300:
                text = clean_html(str(el))
                break
    if not text:
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and len(meta.get("content", "")) > 300:
            text = meta["content"]
    if not text:
        body = soup.select_one("body")
        if body:
            candidate = clean_html(str(body))
            text = candidate if len(candidate) > 500 else ""
    if not text:
        return None
    head = text[:1500].lower()
    if any(t in text[:600].lower() for t in _LISTING_TELLS) or any(t in head for t in _BOT_TELLS):
        return None
    title = None
    h1 = soup.select_one("h1")
    if h1:
        t = h1.get_text(strip=True)
        if 4 < len(t) < 120 and not re.search(r"jobs at|careers|open positions", t, re.I):
            title = t
    return {"description": truncate(text), "title": title}


def _from_json_ld(html: str) -> str:
    import json
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict) and it.get("@type") == "JobPosting" and it.get("description"):
                return clean_html(it["description"])
    return ""

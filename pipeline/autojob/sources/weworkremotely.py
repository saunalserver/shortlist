"""We Work Remotely — category RSS feeds (no key)."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import get_text

NAME = "weworkremotely"
logger = logging.getLogger("autojob")
FEED = "https://weworkremotely.com/categories/{feed}.rss"


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    out: list[RawJob] = []
    seen: set[str] = set()
    for feed in cfg.get("feeds", []):
        try:
            xml = get_text(FEED.format(feed=feed))
            root = ET.fromstring(xml)
        except Exception as e:  # noqa: BLE001
            logger.warning("[wwr] feed %s failed: %s", feed, str(e)[:120])
            continue
        for item in root.iter("item"):
            url = canonical_url(item.findtext("link") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            raw_title = item.findtext("title") or ""
            company, _, title = raw_title.partition(":")
            if not title:
                title, company = raw_title, ""
            desc = clean_html(item.findtext("description") or "")
            out.append(RawJob(
                url=url, title=title.strip(), company=company.strip(), source=NAME,
                location=(item.findtext("region") or "Remote").strip(), description=truncate(desc),
                snippet=snippet_of(desc), employment_type=(item.findtext("type") or None),
                posted_at=(item.findtext("pubDate") or "")[:16] or None, remote=True,
            ))
    logger.info("[wwr] %d jobs", len(out))
    return out

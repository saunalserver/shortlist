"""Company career pages via public ATS APIs (Greenhouse / Lever / Ashby / SmartRecruiters /
Recruitee / Workable / Personio).

Boards come from two places: curated slug lists in config/search.yaml under sources.ats_companies,
and the ``ats_boards`` table (filled by ``scripts/expand_ats_boards.py`` — the LastRound CC-BY
dataset probe). Jobs are kept when the title contains one of ``title_keywords`` and the
location looks like Canada/remote.
"""
from __future__ import annotations

import logging
import time

from autojob import ats
from autojob.db import connect
from autojob.models import RawJob
from autojob.prefilter import CANADA_MARKERS, REMOTE_MARKERS, location_reason
from autojob.settings import Settings
from autojob.sources.base import title_matches

NAME = "ats_companies"
logger = logging.getLogger("autojob")


def location_ok(settings: Settings, loc: str, remote: bool | None) -> bool:
    """Company boards are worldwide, so be stricter than the general prefilter: keep a posting only when it
    names Canada/BC, says remote (and is not pinned elsewhere), or has no location at all."""
    low = f" {(loc or '').lower()} "
    loc_cfg = settings.get("prefilter.location", {}) or {}
    if any(k in low for k in CANADA_MARKERS):
        return location_reason(loc, loc_cfg, remote) is None      # still drops "Toronto, Ontario, Canada"
    if remote or any(k in low for k in REMOTE_MARKERS):
        return location_reason(loc, loc_cfg, True) is None        # drops "Remote - Houston", "Remote - EMEA"
    return not (loc or "").strip()   # empty location → let the LLM judge


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    keywords = list(cfg.get("title_keywords", []))
    cap = int(cfg.get("max_jobs_per_company", 15))
    out: list[RawJob] = []
    boards = [(ats_type, slug, "") for ats_type in ats.FETCHERS for slug in cfg.get(ats_type, []) or []]
    if cfg.get("use_discovered_boards", True):
        with connect() as conn:
            rows = conn.execute("SELECT ats_type, slug, company FROM ats_boards").fetchall()
        boards += [(r["ats_type"], r["slug"], r["company"]) for r in rows if r["ats_type"] in ats.FETCHERS]
    dead: list[str] = []
    for ats_type, slug, company in boards:
        try:
            jobs = ats.fetch_board(ats_type, slug, company, NAME)
        except Exception as e:  # noqa: BLE001
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code == 404:
                dead.append(f"{ats_type}/{slug}")
            else:
                logger.debug("[ats] %s/%s failed: %s", ats_type, slug, str(e)[:100])
            continue
        kept = 0
        for j in jobs:
            if not j.url or not title_matches(j.title, keywords) or not location_ok(settings, j.location, j.remote):
                continue
            out.append(j)
            kept += 1
            if kept >= cap:
                break
        time.sleep(0.2)
    if dead:
        logger.info("[ats] %d boards returned 404 (run `autojob companies verify` to prune): %s", len(dead), ", ".join(dead[:12]))
    logger.info("[ats] %d ops-relevant jobs from %d company boards", len(out), len(boards))
    return out

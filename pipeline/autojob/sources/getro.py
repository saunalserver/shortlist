"""Getro-powered VC portfolio job boards (Atomico, Point Nine, Inovia, Real Ventures…) — no key.

Search: POST https://api.getro.com/api/v2/collections/<id>/search/jobs
        {"hitsPerPage": 20, "page": N, "query": "operations", "filters": {"work_mode": ["remote"], …}}
Needs ``Accept: application/json`` (else 406) plus Origin/Referer set to the board's host.
A board's id is ``__NEXT_DATA__.props.pageProps.network.id`` in its /jobs page.
Rows carry title, organization, work_mode, locations, seniority, created_at and the original
ATS url — no description (the pipeline scrapes it after the prefilter).

Each board has passes (config ``passes``, else ``mode``):
  mode "remote"  — remote jobs a Vancouver resident can do: locations empty, plain "Remote",
                   or naming Canada / North America / Americas / worldwide. A remote job pinned
                   to Europe, Germany, "EMEA"… is a residency restriction → dropped (user, 2026-09-28).
  mode "canada"  — Vancouver-area jobs in any work mode + remote jobs located in Canada.
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from autojob.models import RawJob
from autojob.normalize import canonical_url
from autojob.prefilter import is_local
from autojob.settings import Settings
from autojob.sources.base import session, title_matches

NAME = "getro"
logger = logging.getLogger("autojob")
API = "https://api.getro.com/api/v2/collections/{id}/search/jobs"
PAGE = 20
DEFAULT_QUERIES = ["operations", "coordinator", "analyst", "specialist"]
DEFAULT_SENIORITY = ["entry_level", "associate", "mid_senior"]
# A remote row whose locations name one of these is open to someone living in Vancouver.
REMOTE_OK = ("canada", "north america", "americas", "worldwide", "anywhere", "global")
_GENERIC = {"remote", "remote first", "distributed", "work from home"}


def remote_open_to_vancouver(locations: list[str]) -> bool:
    locs = [str(x).strip().lower() for x in locations or [] if str(x).strip()]
    if not locs:
        return True
    if any(any(k in loc for k in REMOTE_OK) for loc in locs):
        return True
    if any(", bc" in loc or "british columbia" in loc for loc in locs):
        return True
    return all(loc in _GENERIC for loc in locs)   # plain "Remote", no region named


def canada_keep(job: dict) -> tuple[bool, bool]:
    """(keep, remote) for the Canada-fund pass: Vancouver area any mode, or remote in Canada."""
    locs = [str(x).lower() for x in job.get("locations") or []]
    remote = job.get("work_mode") == "remote"
    if any(is_local(loc) for loc in locs):
        return True, remote
    if remote and any("canada" in loc or ", bc" in loc for loc in locs):
        return True, True
    return False, remote


def _location_text(job: dict) -> str:
    locs = [str(x) for x in job.get("locations") or [] if str(x).strip()]
    text = ", ".join(locs) or "Remote"
    if job.get("work_mode") == "remote" and "remote" not in text.lower():
        text += " (remote)"
    return text


def _epoch_date(v) -> str | None:
    try:
        return datetime.fromtimestamp(int(v), UTC).strftime("%Y-%m-%d") if v else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _search(board: dict, query: str, filters: dict, page: int) -> dict:
    host = board["host"]
    headers = {"Accept": "application/json", "Content-Type": "application/json",
               "Origin": f"https://{host}", "Referer": f"https://{host}/jobs"}
    body = {"hitsPerPage": PAGE, "page": page, "query": query, "filters": filters}
    resp = session().post(API.format(id=board["id"]), json=body, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json().get("results") or {}


def _passes(board: dict) -> list[dict]:
    mode = board.get("mode", "remote")
    if mode == "canada":
        return [{"mode": "canada", "filters": {"searchable_locations": ["British Columbia, Canada"]}},
                {"mode": "canada", "filters": {"searchable_locations": ["Canada"], "work_mode": ["remote"]}}]
    return [{"mode": "remote", "filters": {"work_mode": ["remote"]}}]


def to_raw(job: dict, board_name: str, remote: bool) -> RawJob | None:
    url = canonical_url(job.get("url") or "")
    if not url:
        return None
    org = job.get("organization") or {}
    lo, hi = job.get("compensation_amount_min_cents"), job.get("compensation_amount_max_cents")
    period = job.get("compensation_period")
    return RawJob(
        url=url, title=(job.get("title") or "").strip(), company=org.get("name", ""), source=NAME,
        location=_location_text(job),
        salary_min=lo / 100 if lo and period == "year" else None,
        salary_max=hi / 100 if hi and period == "year" else None,
        salary_currency=job.get("compensation_currency") if period == "year" else None,
        posted_at=_epoch_date(job.get("created_at")), remote=True if remote else None,
        extra={"board": board_name, "seniority": job.get("seniority"), "work_mode": job.get("work_mode")},
    )


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    queries = list(cfg.get("queries") or DEFAULT_QUERIES)
    seniority = list(cfg.get("seniority") or DEFAULT_SENIORITY)
    title_kw = list(cfg.get("title_keywords") or settings.source("workday").get("title_keywords") or [])
    max_age = int(cfg.get("max_age_days", 14))
    pages = int(cfg.get("pages_per_query", 2))
    cutoff = time.time() - max_age * 86400
    out: list[RawJob] = []
    seen: set[str] = set()
    for board in cfg.get("boards", []) or []:
        kept = dropped_loc = dropped_other = 0
        for p in _passes(board):
            filters = {**p["filters"], "seniority": seniority}
            for q in board.get("queries") or queries:
                for page in range(pages):
                    try:
                        res = _search(board, q, filters, page)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("[getro] %s '%s' p%d failed: %s", board.get("name"), q, page, str(e)[:120])
                        break
                    jobs = res.get("jobs") or []
                    for j in jobs:
                        key = j.get("url") or str(j.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        if (j.get("created_at") or 0) < cutoff or (title_kw and not title_matches(j.get("title", ""), title_kw)):
                            dropped_other += 1
                            continue
                        if p["mode"] == "canada":
                            keep, remote = canada_keep(j)
                        else:
                            keep, remote = remote_open_to_vancouver(j.get("locations") or []), True
                        if not keep:
                            dropped_loc += 1
                            continue
                        raw = to_raw(j, board.get("name", ""), remote)
                        if raw:
                            out.append(raw)
                            kept += 1
                    if len(jobs) < PAGE:
                        break
                    time.sleep(float(cfg.get("delay_s", 0.4)))
        logger.info("[getro] %s: %d kept, %d dropped for location/residency, %d off-title/too old",
                    board.get("name"), kept, dropped_loc, dropped_other)
    logger.info("[getro] %d jobs from %d boards", len(out), len(cfg.get("boards", []) or []))
    return out

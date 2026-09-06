"""Google results via serper.dev. Credits are finite (2,500 on the free tier), so each run
executes only ``queries_per_run`` searches, rotating through the plan across runs."""
from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from autojob.models import RawJob
from autojob.normalize import canonical_url, snippet_of
from autojob.settings import Settings
from autojob.sources.base import post_json

NAME = "serper"
logger = logging.getLogger("autojob")
SERPER_URL = "https://google.serper.dev/search"

# Only keep URLs that look like a single posting.
_INDIVIDUAL = [
    (re.compile(r"linkedin\.com/jobs/view/\d+"), "linkedin"),
    (re.compile(r"indeed\.com/(viewjob|rc/clk|m/viewjob)"), "indeed"),
    (re.compile(r"glassdoor\.[a-z.]+/job-listing/"), "glassdoor"),
    (re.compile(r"wellfound\.com/jobs/\d+"), "wellfound"),
    (re.compile(r"greenhouse\.io/[^/]+/jobs/\d+"), "greenhouse"),
    (re.compile(r"jobs\.lever\.co/[^/]+/[0-9a-f-]{20,}"), "lever"),
    (re.compile(r"jobs\.ashbyhq\.com/[^/]+/[0-9a-f-]{20,}"), "ashby"),
    (re.compile(r"apply\.workable\.com/[^/]+/j/"), "workable"),
    (re.compile(r"jobs\.smartrecruiters\.com/[^/]+/\d+"), "smartrecruiters"),
    (re.compile(r"myworkdayjobs\.com/.+/job/"), "workday"),
    (re.compile(r"jobbank\.gc\.ca/jobposting/\d+"), "jobbank"),
    (re.compile(r"bcjobs\.ca/jobs/\d+"), "bcjobs"),
    (re.compile(r"ziprecruiter\.com/c/[^/]+/Job/"), "ziprecruiter"),
]
_LISTING_TITLE = re.compile(
    r"\d[\d,]*\+\s|current openings|^jobs at\b|^careers?\b|open positions|job listings|hiring \d+|\bjobs in \w+|\bjobs near\b",
    re.I,
)
_SUFFIX = re.compile(
    r"\s*[-–—|]\s*(Indeed\.com|Indeed|LinkedIn|Glassdoor|ZipRecruiter|Wellfound|SimplyHired|Jobcase|Greenhouse|Lever|"
    r"Myworkdayjobs\.com|Workable Jobs|Workable|SmartRecruiters|Careers?|Jobs?|Job Board|Ashby)\s*$", re.I)


def _company_from_url(url: str) -> str:
    path = urlsplit(url).path.strip("/").split("/")
    host = urlsplit(url).netloc
    if ("greenhouse.io" in host or "lever.co" in host or "ashbyhq.com" in host or "workable.com" in host) and path:
        return path[0].replace("-", " ").replace("_", " ").title()
    if "myworkdayjobs.com" in host:
        return host.split(".")[0].replace("-", " ").title()
    return ""


def _location_from_url(url: str) -> str:
    """Workday URLs carry the location: …/job/UBC-Vancouver-Campus---Vancouver-BC-Canada/Title_JR123."""
    if "myworkdayjobs.com" not in url:
        return ""
    m = re.search(r"/job/([^/]+)/[^/]+$", urlsplit(url).path)
    if not m:
        return ""
    return m.group(1).replace("---", ", ").replace("-", " ").strip()


def _clean_title(title: str) -> str:
    t = title
    for _ in range(3):   # "Ops Analyst - Careers - Myworkdayjobs.com" has two suffixes
        new = _SUFFIX.sub("", t).strip()
        if new == t:
            break
        t = new
    return t


def _looks_individual(url: str) -> bool:
    return any(rx.search(url) for rx, _ in _INDIVIDUAL)


def fetch(settings: Settings) -> list[RawJob]:
    key = settings.secrets.serper_api_key
    if not key:
        logger.info("[serper] no API key, skipping")
        return []
    cfg = settings.source(NAME)
    queries = settings.source_queries(NAME)
    plan_items: list[tuple[str, str]] = []
    for step in cfg.get("plan", []) or []:
        qs = step.get("queries")
        qs = queries if qs in (None, "default") else list(qs)
        for q in qs:
            plan_items.append((q, step.get("suffix", "")))
    if not plan_items:
        return []
    budget = int(cfg.get("queries_per_run", 12))
    offset = _rotation_offset(len(plan_items), budget)
    batch = [plan_items[(offset + i) % len(plan_items)] for i in range(min(budget, len(plan_items)))]

    out: list[RawJob] = []
    seen: set[str] = set()
    credits_used = 0
    for q, suffix in batch:
        full = f"{q} {suffix}".strip()
        payload = {"q": full, "num": int(cfg.get("results_per_query", 20))}  # gl/hl are rejected on the free tier
        if cfg.get("recency"):
            payload["tbs"] = cfg["recency"]
        try:
            data = post_json(SERPER_URL, json=payload, headers={"X-API-KEY": key})
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            logger.warning("[serper] '%s' failed: %s", full, msg[:160])
            if "402" in msg or "403" in msg or "Not enough credits" in msg:
                logger.error("[serper] credits exhausted or key invalid — stopping serper for this run")
                break
            continue
        credits_used += int(data.get("credits", 1) or 1)
        for item in data.get("organic", []):
            link = item.get("link", "")
            title = _clean_title(item.get("title", ""))
            if not link or not _looks_individual(link) or _LISTING_TITLE.search(title or ""):
                continue
            url = canonical_url(link)
            if url in seen:
                continue
            seen.add(url)
            out.append(RawJob(url=url, title=title, company=_company_from_url(link), source=NAME,
                              location=_location_from_url(link), snippet=snippet_of(item.get("snippet", ""))))
    logger.info("[serper] %d jobs from %d searches (%d credits)", len(out), len(batch), credits_used)
    if credits_used:
        _track_credits(credits_used)
    return out


def _track_credits(credits: int) -> None:
    """Cumulative spend counter in the meta table — the dashboard shows total minus this.
    No serper balance API exists, so we account locally."""
    try:
        from autojob.db import connect
        with connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT INTO meta(key, value) VALUES('serper_credits_used', '0') ON CONFLICT(key) DO NOTHING")
            conn.execute("UPDATE meta SET value = CAST(value AS INTEGER) + ? WHERE key = 'serper_credits_used'", (credits,))
    except Exception as e:  # noqa: BLE001
        logger.warning("[serper] could not record credit spend: %s", str(e)[:120])


def _rotation_offset(n_items: int, budget: int) -> int:
    """Advance through the plan run after run using the run count in the DB."""
    try:
        from autojob.db import connect
        with connect() as conn:
            runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    except Exception:  # noqa: BLE001
        runs = 0
    return (runs * budget) % max(n_items, 1)

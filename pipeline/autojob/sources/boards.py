"""LinkedIn + Indeed via python-jobspy (no key). Indeed returns full descriptions; LinkedIn
descriptions are fetched per job when ``linkedin_fetch_description`` is on."""
from __future__ import annotations

import logging
import warnings

from autojob.models import RawJob
from autojob.normalize import canonical_url, clean_html, snippet_of, truncate
from autojob.settings import Settings

NAME = "boards"
logger = logging.getLogger("autojob")


def _s(v) -> str:
    if v is None:
        return ""
    s = str(v)
    return "" if s in ("nan", "None", "NaT") else s


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.error("[boards] python-jobspy not installed")
        return []
    logging.getLogger("JobSpy").setLevel(logging.ERROR)
    out: list[RawJob] = []
    seen: set[str] = set()
    for term in settings.source_queries(NAME)[: int(cfg.get("max_queries", 10))]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = scrape_jobs(
                    site_name=list(cfg.get("sites", ["linkedin", "indeed"])),
                    search_term=term,
                    location=cfg.get("location", "Vancouver, BC"),
                    results_wanted=int(cfg.get("results_per_query", 15)),
                    hours_old=int(cfg.get("hours_old", 72)),
                    country_indeed=cfg.get("country_indeed", "canada"),
                    linkedin_fetch_description=bool(cfg.get("linkedin_fetch_description", True)),
                    description_format="markdown",
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("[boards] '%s' failed: %s", term, str(e)[:160])
            continue
        for _, row in df.iterrows():
            url = canonical_url(_s(row.get("job_url")) or _s(row.get("job_url_direct")))
            if not url or url in seen:
                continue
            seen.add(url)
            desc = clean_html(_s(row.get("description")))
            is_remote = row.get("is_remote")
            out.append(RawJob(
                url=url, title=_s(row.get("title")), company=_s(row.get("company")), source=NAME,
                location=_s(row.get("location")), description=truncate(desc), snippet=snippet_of(desc),
                salary_min=_num(row.get("min_amount")), salary_max=_num(row.get("max_amount")),
                salary_currency=_s(row.get("currency")) or None, employment_type=_s(row.get("job_type")) or None,
                posted_at=_s(row.get("date_posted"))[:10] or None,
                remote=bool(is_remote) if is_remote is not None and _s(is_remote) not in ("", "nan") else None,
            ))
    logger.info("[boards] %d jobs from %s", len(out), "+".join(cfg.get("sites", [])))
    return out


def _num(v) -> float | None:
    try:
        f = float(v)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None

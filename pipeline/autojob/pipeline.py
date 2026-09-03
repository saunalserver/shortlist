"""The daily run: fetch → dedupe → prefilter → scrape → score → (auto-docs) → digest.

Sequential and boring on purpose. Abort is a flag in ``pipeline_state.command``
checked between jobs, so the dashboard can stop a run from another process.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from typing import Any

from autojob import db as D
from autojob import sources as S
from autojob.llm import LLM, LLMBudgetExceeded
from autojob.models import RawJob
from autojob.prefilter import prefilter_reason
from autojob.scraper import scrape
from autojob.settings import LOCK_PATH, LOG_PATH, Settings, ensure_dirs

logger = logging.getLogger("autojob")


class Aborted(Exception):
    pass


class AlreadyRunning(RuntimeError):
    pass


@dataclass
class RunSummary:
    run_id: int
    dry_run: bool
    fetched: int = 0
    new_jobs: int = 0
    dup_url: int = 0
    dup_fp: int = 0
    prefiltered: int = 0
    scraped: int = 0
    scored: int = 0
    queued: int = 0
    skipped: int = 0
    docs: int = 0
    errors: int = 0
    llm_calls: int = 0
    expired: int = 0
    per_source: dict[str, dict[str, Any]] = field(default_factory=dict)
    status: str = "running"

    def as_row(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in ("fetched", "new_jobs", "prefiltered", "scored", "queued", "skipped",
                                              "docs", "errors", "llm_calls", "expired")}


def setup_logging(verbose: bool = False) -> None:
    if logger.handlers:
        return
    ensure_dirs()
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh = RotatingFileHandler(str(LOG_PATH), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    fh.setLevel(logging.INFO)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(sh)


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock() -> None:
    ensure_dirs()
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text().strip() or 0)
        except ValueError:
            pid = 0
        if pid and _pid_alive(pid):
            raise AlreadyRunning(f"another run is in progress (pid {pid})")
        logger.warning("stale lock from pid %s — taking over", pid)
    LOCK_PATH.write_text(str(os.getpid()))


def release_lock() -> None:
    LOCK_PATH.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _check_abort(conn) -> None:
    if D.consume_abort(conn):
        raise Aborted()


def expire_stale(settings: Settings, conn, summary: RunSummary, dry_run: bool = False) -> None:
    """Retire shortlisted postings that are too old or whose page is gone (see autojob/expire.py)."""
    from autojob.expire import expire

    cfg = settings.get("expiry", {}) or {}
    res = expire(conn, posted_max_days=int(cfg.get("posted_max_days", 30)),
                 fetched_max_days=int(cfg.get("fetched_max_days", 45)),
                 link_checks=int(cfg.get("link_checks_per_run", 0)), dry_run=dry_run)
    summary.expired = len(res["ids"])


def fetch_all(settings: Settings, conn, run_id: int, only: list[str] | None, summary: RunSummary) -> list[RawJob]:
    jobs: list[RawJob] = []
    for name in S.enabled(settings, only):
        _check_abort(conn)
        D.set_pipeline_state(conn, current_phase=f"fetching:{name}")
        conn.commit()
        started = D.now_iso()
        t0 = time.monotonic()
        err = None
        got: list[RawJob] = []
        try:
            got = S.load(name).fetch(settings)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:200]}"
            logger.error("[%s] source failed: %s", name, err)
        dur = time.monotonic() - t0
        for j in got:
            j.source = j.source or name
        jobs.extend(got)
        summary.per_source[name] = {"fetched": len(got), "duration_s": round(dur, 1), "error": err, "started_at": started}
        logger.info("[%s] %d jobs in %.0fs", name, len(got), dur)
    summary.fetched = len(jobs)
    return jobs


def insert(conn, jobs: list[RawJob], run_id: int, summary: RunSummary) -> list[int]:
    new_ids, dup_url, dup_fp = D.insert_jobs(conn, jobs, run_id)
    conn.commit()
    summary.new_jobs, summary.dup_url, summary.dup_fp = len(new_ids), dup_url, dup_fp
    # per-source new counts
    if new_ids:
        rows = conn.execute(
            f"SELECT source, COUNT(*) c FROM jobs WHERE id IN ({','.join('?' * len(new_ids))}) GROUP BY source",  # noqa: S608
            new_ids,
        ).fetchall() if len(new_ids) <= 900 else conn.execute(
            "SELECT source, COUNT(*) c FROM jobs WHERE run_id = ? GROUP BY source", (run_id,)).fetchall()
        for r in rows:
            summary.per_source.setdefault(r["source"], {})["new"] = r["c"]
    logger.info("inserted %d new jobs (%d already seen, %d duplicate title+company)", len(new_ids), dup_url, dup_fp)
    return new_ids


def prefilter(settings: Settings, conn, jobs: list[dict[str, Any]], summary: RunSummary) -> list[dict[str, Any]]:
    cfg = settings.get("prefilter", {}) or {}
    keep: list[dict[str, Any]] = []
    for j in jobs:
        reason = prefilter_reason(j, cfg)
        if reason:
            D.update_job(conn, j["id"], status=D.STATUS_PREFILTERED, prefilter_reason=reason, processed_at=D.now_iso())
            summary.prefiltered += 1
        else:
            keep.append(j)
    conn.commit()
    logger.info("prefilter: %d dropped, %d kept for scoring", summary.prefiltered, len(keep))
    return keep


def scrape_missing(settings: Settings, conn, jobs: list[dict[str, Any]], summary: RunSummary) -> None:
    budget = int(settings.get("scoring.max_scrapes_per_run", 150))
    todo = [j for j in jobs if len((j.get("description") or "").strip()) < 200]
    logger.info("scraping descriptions for %d/%d jobs (budget %d)", min(len(todo), budget), len(jobs), budget)
    for j in todo[:budget]:
        _check_abort(conn)
        res = scrape(j["url"])
        if res and res.get("description"):
            fields: dict[str, Any] = {"description": res["description"], "description_length": len(res["description"])}
            if res.get("title") and len(res["title"]) > 4 and (not j.get("title") or len(j["title"]) < 6):
                fields["title"] = res["title"]
            D.update_job(conn, j["id"], **fields)
            j.update(fields)
            summary.scraped += 1
    conn.commit()
    logger.info("scraped %d descriptions", summary.scraped)


def score_jobs(settings: Settings, conn, jobs: list[dict[str, Any]], llm: LLM, summary: RunSummary) -> list[int]:
    from autojob.scorer import Scorer

    scorer = Scorer(settings, llm)
    threshold = int(settings.get("scoring.min_score_to_queue", 6))
    queued: list[int] = []
    D.set_pipeline_state(conn, current_phase="scoring", jobs_total=len(jobs), jobs_processed=0)
    conn.commit()
    for i, j in enumerate(jobs, 1):
        _check_abort(conn)
        try:
            res = scorer.score(j)
        except LLMBudgetExceeded as e:
            logger.warning("%s — remaining jobs stay 'new' for the next run", e)
            break
        summary.scored += 1
        if res is None:
            D.update_job(conn, j["id"], status=D.STATUS_ERROR, processed_at=D.now_iso())
            summary.errors += 1
        else:
            fields = dict(
                company=res.get("company") or j.get("company"), fit_score=res["fit_score"],
                fit_reasoning=res.get("one_liner", ""), strengths=json.dumps(res["strengths"], ensure_ascii=False),
                gaps=json.dumps(res["gaps"], ensure_ascii=False), low_confidence=int(res["low_confidence"]),
                scored_at=D.now_iso(), processed_at=D.now_iso(), scorer_model=res.get("model"),
                description_length=len(j.get("description") or ""),
            )
            if res["skip"] or res["fit_score"] < threshold:
                fields.update(status=D.STATUS_SKIPPED, skip_reason=res.get("skip_reason") or f"score {res['fit_score']} < {threshold}")
                summary.skipped += 1
            else:
                fields.update(status=D.STATUS_QUEUED, skip_reason=None)
                queued.append(j["id"])
            D.update_job(conn, j["id"], **fields)
            logger.info("scored %s/10 %s — %s at %s [%s]", res["fit_score"], "SKIP" if res["skip"] else "    ",
                        j.get("title"), fields["company"], res.get("model"))
        D.set_pipeline_state(conn, jobs_processed=i)
        conn.commit()
    summary.llm_calls = llm.calls
    summary.queued = len(queued)
    return queued


def generate_docs_for(settings: Settings, conn, job_ids: list[int], summary: RunSummary | None = None) -> int:
    """Generate resume + cover letter for the given jobs (used by the run and by the worker/CLI)."""
    from autojob.docs import DocGenerator

    if not job_ids:
        return 0
    llm = LLM(settings.secrets.llm_api_key, settings.secrets.llm_base_url, settings.get("scoring.docs_models", []))
    gen = DocGenerator(settings, llm)
    done = 0
    for jid in job_ids:
        _check_abort(conn)
        job = D.get_job(conn, jid)
        if not job:
            continue
        for key in ("strengths", "gaps"):
            try:
                job[key] = json.loads(job[key]) if isinstance(job.get(key), str) else job.get(key)
            except json.JSONDecodeError:
                pass
        try:
            folder, resume_ok, cl_ok = gen.generate(job)
        except Exception as e:  # noqa: BLE001
            logger.error("doc generation failed for job %s: %s", jid, str(e)[:200])
            if summary:
                summary.errors += 1
            continue
        if resume_ok:
            D.update_job(conn, jid, status=D.STATUS_DOCS, output_folder=str(folder), docs_generated_at=D.now_iso())
            done += 1
            logger.info("docs ready for %s at %s → %s%s", job.get("title"), job.get("company"), folder,
                        "" if cl_ok else " (cover letter failed)")
        else:
            logger.error("resume PDF missing for job %s", jid)
            if summary:
                summary.errors += 1
        conn.commit()
    if summary:
        summary.docs += done
        summary.llm_calls += llm.calls
    return done


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _install_sigterm_abort() -> None:
    import signal

    def _on_term(*_):
        try:
            with D.db() as conn:
                D.set_pipeline_state(conn, command="abort")
        except Exception:  # noqa: BLE001
            pass

    try:
        signal.signal(signal.SIGTERM, _on_term)
    except ValueError:  # not in the main thread
        pass


def run(settings: Settings, *, dry_run: bool = False, only_sources: list[str] | None = None,
        no_docs: bool = False, no_notify: bool = False, max_jobs: int | None = None) -> RunSummary:
    setup_logging()
    D.init_db()
    acquire_lock()
    _install_sigterm_abort()
    conn = D.connect()
    run_id = D.start_run(conn, dry_run)
    summary = RunSummary(run_id=run_id, dry_run=dry_run)
    D.set_pipeline_state(conn, status="running", started_at=D.now_iso(), current_phase="init", jobs_total=0,
                         jobs_processed=0, command=None, run_id=run_id, pid=os.getpid())
    conn.commit()
    logger.info("=== autojob run %d starting%s ===", run_id, " (DRY RUN)" if dry_run else "")
    t0 = time.monotonic()
    started_at = D.now_iso()
    try:
        # 0. retire old / dead shortlisted postings so the review queue only holds live ones
        if not only_sources:
            D.set_pipeline_state(conn, current_phase="expiring")
            conn.commit()
            expire_stale(settings, conn, summary, dry_run=dry_run)
        # 1. fetch
        raw = fetch_all(settings, conn, run_id, only_sources, summary)
        # 2. insert
        D.set_pipeline_state(conn, current_phase="inserting")
        new_ids = insert(conn, raw, run_id, summary)
        for name, info in summary.per_source.items():
            D.record_source_run(conn, run_id, name, info.get("started_at", D.now_iso()), info.get("duration_s", 0.0),
                                info.get("fetched", 0), info.get("new", 0), info.get("error"))
        conn.commit()
        # carry-over: anything still 'new' or 'error' from earlier runs
        candidates = D.get_jobs(conn, new_ids)
        carry = [j for j in D.jobs_with_status(conn, D.STATUS_NEW) + D.jobs_with_status(conn, D.STATUS_ERROR)
                 if j["id"] not in set(new_ids)]
        if carry:
            logger.info("carrying over %d unscored jobs from earlier runs", len(carry))
        candidates += carry
        if max_jobs:
            candidates = candidates[:max_jobs]
        # 3. prefilter
        D.set_pipeline_state(conn, current_phase="prefiltering")
        conn.commit()
        candidates = prefilter(settings, conn, candidates, summary)
        # 4. scrape
        D.set_pipeline_state(conn, current_phase="scraping")
        conn.commit()
        scrape_missing(settings, conn, candidates, summary)
        # 5. score
        if candidates:
            llm = LLM(settings.secrets.llm_api_key, settings.secrets.llm_base_url, settings.get("scoring.models", []),
                      max_calls=int(settings.get("scoring.max_llm_calls_per_run", 400)))
            queued_ids = score_jobs(settings, conn, candidates, llm, summary)
        else:
            queued_ids = []
        logger.info("scoring: %d queued, %d skipped, %d errors (%d LLM calls)", summary.queued, summary.skipped,
                    summary.errors, summary.llm_calls)
        # 6. auto docs
        if not dry_run and not no_docs and queued_ids:
            min_auto = int(settings.get("scoring.auto_docs_min_score", 8))
            auto = [j["id"] for j in D.get_jobs(conn, queued_ids) if (j.get("fit_score") or 0) >= min_auto]
            if auto:
                D.set_pipeline_state(conn, current_phase="generating", jobs_total=len(auto), jobs_processed=0)
                conn.commit()
                logger.info("auto-generating documents for %d jobs scoring ≥ %d", len(auto), min_auto)
                generate_docs_for(settings, conn, auto, summary)
        # 7. notify
        summary.status = "done"
        D.finish_run(conn, run_id, "done", **summary.as_row())
        conn.commit()
        if not dry_run and not no_notify:
            from autojob.notify import send_digest
            D.set_pipeline_state(conn, current_phase="notifying")
            conn.commit()
            run_row = dict(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())
            # everything shortlisted by this run's scoring — including carry-over jobs fetched by an earlier run
            send_digest(settings, run_row, D.queued_since(conn, started_at))
        D.set_pipeline_state(conn, status="idle", current_phase="done")
    except Aborted:
        summary.status = "aborted"
        logger.warning("run %d aborted by user", run_id)
        D.finish_run(conn, run_id, "aborted", **summary.as_row())
        D.set_pipeline_state(conn, status="idle", current_phase="aborted")
    except AlreadyRunning:
        raise
    except Exception as e:  # noqa: BLE001
        summary.status = "error"
        logger.exception("run %d failed: %s", run_id, e)
        D.finish_run(conn, run_id, "error", notes=str(e)[:500], **summary.as_row())
        D.set_pipeline_state(conn, status="idle", current_phase="error")
        if not no_notify:
            try:
                from autojob.notify import send_alert
                send_alert(settings, f"Run {run_id} failed: {e}")
            except Exception:  # noqa: BLE001
                pass
    finally:
        conn.commit()
        conn.close()
        release_lock()
        logger.info("=== run %d %s in %.0f min: %d fetched, %d new, %d prefiltered, %d scored, %d queued, %d docs, "
                    "%d errors, %d expired ===",
                    run_id, summary.status, (time.monotonic() - t0) / 60, summary.fetched, summary.new_jobs,
                    summary.prefiltered, summary.scored, summary.queued, summary.docs, summary.errors, summary.expired)
    return summary

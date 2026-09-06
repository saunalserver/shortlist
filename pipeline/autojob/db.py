"""SQLite storage. Jobs are never deleted: that is what makes dedup and "don't re-score" work.

Tables
------
jobs            one row per unique posting URL, with pipeline status + LLM verdict + user action
seen_urls       every URL ever fetched (survives everything; cheap dedup set)
company_ats_cache  which ATS (greenhouse/lever/ashby/none) a company slug uses
runs / source_runs  per-run and per-source counters for stats and the dashboard
pipeline_state  single row read by the dashboard (status, phase, progress, abort flag)
commands        queue written by the dashboard, consumed by ``autojob worker``
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autojob.models import RawJob
from autojob.normalize import fingerprint
from autojob.settings import DB_PATH

logger = logging.getLogger("autojob")

SCHEMA_VERSION = 3

# Status lifecycle for jobs.status
STATUS_NEW = "new"                    # fetched, not yet scored
STATUS_PREFILTERED = "prefiltered"    # rejected by cheap rules, never sent to the LLM
STATUS_SKIPPED = "skipped"            # LLM said skip / below threshold
STATUS_QUEUED = "queued"              # LLM says worth a look — awaiting your decision
STATUS_DOCS = "docs_generated"        # resume + cover letter exist in output_folder
STATUS_ERROR = "error"                # scoring failed; retried on the next run
STATUS_EXPIRED = "expired"            # was queued/docs, but the posting is old or gone (see skip_reason)

ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_DOCS)   # what "to review" means everywhere

JOB_COLUMNS = {
    "url", "title", "snippet", "description", "company", "location", "source",
    "salary_min", "salary_max", "salary_currency", "employment_type", "posted_at", "remote",
    "fingerprint", "fit_score", "fit_reasoning", "strengths", "gaps", "skip_reason",
    "prefilter_reason", "status", "fetched_at", "processed_at", "scored_at", "scorer_model",
    "low_confidence", "description_length", "output_folder", "docs_generated_at",
    "user_action", "user_action_at", "run_id", "link_checked_at",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema + migration
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    snippet TEXT,
    description TEXT,
    company TEXT,
    location TEXT,
    source TEXT,
    salary_min REAL,
    salary_max REAL,
    salary_currency TEXT,
    employment_type TEXT,
    posted_at TEXT,
    remote INTEGER,
    fingerprint TEXT,
    fit_score INTEGER,
    fit_reasoning TEXT,
    strengths TEXT,
    gaps TEXT,
    skip_reason TEXT,
    prefilter_reason TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    fetched_at TEXT NOT NULL,
    processed_at TEXT,
    scored_at TEXT,
    scorer_model TEXT,
    low_confidence INTEGER DEFAULT 0,
    description_length INTEGER,
    output_folder TEXT,
    docs_generated_at TEXT,
    user_action TEXT,
    user_action_at TEXT,
    run_id INTEGER,
    link_checked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint);
CREATE INDEX IF NOT EXISTS idx_jobs_fetched ON jobs(fetched_at);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(fit_score);

CREATE TABLE IF NOT EXISTS seen_urls (
    url TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_ats_cache (
    company_slug TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    ats_type TEXT,
    ats_base_url TEXT,
    last_probed TEXT,
    probe_count INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ats_boards (
    ats_type TEXT NOT NULL,
    slug TEXT NOT NULL,
    company TEXT NOT NULL,
    url TEXT,
    canada_jobs INTEGER DEFAULT 0,
    added TEXT,
    PRIMARY KEY (ats_type, slug)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    dry_run INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    fetched INTEGER DEFAULT 0,
    new_jobs INTEGER DEFAULT 0,
    prefiltered INTEGER DEFAULT 0,
    scored INTEGER DEFAULT 0,
    queued INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    docs INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    llm_calls INTEGER DEFAULT 0,
    notes TEXT,
    expired INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS source_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    duration_s REAL,
    fetched INTEGER DEFAULT 0,
    new_jobs INTEGER DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_runs_source ON source_runs(source, started_at);

CREATE TABLE IF NOT EXISTS pipeline_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    status TEXT DEFAULT 'idle',
    started_at TEXT,
    current_phase TEXT,
    jobs_total INTEGER,
    jobs_processed INTEGER,
    log_tail TEXT,
    command TEXT,
    run_id INTEGER,
    pid INTEGER
);
INSERT OR IGNORE INTO pipeline_state (id, status) VALUES (1, 'idle');

CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    arg TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    status TEXT DEFAULT 'pending',
    result TEXT
);
"""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def init_db(path: Path | None = None) -> None:
    """Create or migrate the database in place. Safe to call on every run."""
    with db(path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        legacy = _table_exists(conn, "jobs") and version == 0
        if legacy:
            _migrate_v1_columns(conn)   # columns must exist before the indexes in _SCHEMA
        conn.executescript(_SCHEMA)
        if legacy:
            _migrate_v1_backfill(conn)
        # pipeline_state columns added in v2
        for col, typ in (("run_id", "INTEGER"), ("pid", "INTEGER")):
            if col not in _columns(conn, "pipeline_state"):
                conn.execute(f"ALTER TABLE pipeline_state ADD COLUMN {col} {typ}")
        # v3: expiry support + looser company key in fingerprints
        if "link_checked_at" not in _columns(conn, "jobs"):
            conn.execute("ALTER TABLE jobs ADD COLUMN link_checked_at TEXT")
        if "expired" not in _columns(conn, "runs"):
            conn.execute("ALTER TABLE runs ADD COLUMN expired INTEGER DEFAULT 0")
        if 0 < version < 3:
            _recompute_fingerprints(conn)
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def _recompute_fingerprints(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id, title, company FROM jobs").fetchall()
    for r in rows:
        conn.execute("UPDATE jobs SET fingerprint = ? WHERE id = ?", (fingerprint(r["title"], r["company"]), r["id"]))
    logger.info("Recomputed %d fingerprints (schema v3)", len(rows))


def _migrate_v1_columns(conn: sqlite3.Connection) -> None:
    """Upgrade an autojob 1.x database (April–June 2026 layout): add the v2 columns."""
    logger.info("Migrating v1 database to schema v2")
    have = _columns(conn, "jobs")
    added = {
        "location": "TEXT", "source": "TEXT", "salary_min": "REAL", "salary_max": "REAL",
        "salary_currency": "TEXT", "employment_type": "TEXT", "posted_at": "TEXT", "remote": "INTEGER",
        "fingerprint": "TEXT", "prefilter_reason": "TEXT", "scored_at": "TEXT", "scorer_model": "TEXT",
        "docs_generated_at": "TEXT", "user_action": "TEXT", "user_action_at": "TEXT", "run_id": "INTEGER",
    }
    for col, typ in added.items():
        if col not in have:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {typ}")


def _migrate_v1_backfill(conn: sqlite3.Connection) -> None:
    # Backfill source from URL host, fingerprints from title+company, docs timestamp.
    rows = conn.execute("SELECT id, url, title, company, status, processed_at FROM jobs").fetchall()
    for r in rows:
        conn.execute(
            "UPDATE jobs SET source = COALESCE(source, ?), fingerprint = ?, "
            "docs_generated_at = CASE WHEN status='docs_generated' THEN COALESCE(docs_generated_at, processed_at, fetched_at) END "
            "WHERE id = ?",
            (_source_from_url(r["url"]), fingerprint(r["title"], r["company"]), r["id"]),
        )
    conn.execute("INSERT OR IGNORE INTO seen_urls (url, first_seen) SELECT url, fetched_at FROM jobs")
    if _table_exists(conn, "job_fingerprints"):
        conn.execute("DROP TABLE job_fingerprints")
    # v1 'queued' jobs never got docs; keep them visible as queued. 'new' unscored → stays new.
    logger.info("Migration done: %d jobs carried over", len(rows))


def _source_from_url(url: str) -> str:
    u = (url or "").lower()
    table = (
        ("adzuna", "adzuna"), ("linkedin.com", "boards"), ("indeed.com", "boards"), ("himalayas.app", "himalayas"),
        ("jooble.org", "jooble"), ("jobbank.gc.ca", "jobbank"), ("remoteok.com", "remoteok"), ("remotive", "remotive"),
        ("greenhouse.io", "ats_companies"), ("lever.co", "ats_companies"), ("ashbyhq.com", "ats_companies"),
        ("ycombinator.com", "yc"),
    )
    for needle, name in table:
        if needle in u:
            return name
    return "serper"


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def insert_jobs(conn: sqlite3.Connection, jobs: Iterable[RawJob], run_id: int | None) -> tuple[list[int], int, int]:
    """Insert unseen jobs. Returns (new_ids, skipped_seen_url, skipped_fingerprint)."""
    new_ids: list[int] = []
    dup_url = dup_fp = 0
    now = now_iso()
    for job in jobs:
        if not job.url or not job.title:
            continue
        if conn.execute("SELECT 1 FROM seen_urls WHERE url = ?", (job.url,)).fetchone():
            dup_url += 1
            continue
        fp = fingerprint(job.title, job.company)
        if fp and conn.execute("SELECT 1 FROM jobs WHERE fingerprint = ? LIMIT 1", (fp,)).fetchone():
            dup_fp += 1
            conn.execute("INSERT OR IGNORE INTO seen_urls (url, first_seen) VALUES (?, ?)", (job.url, now))
            continue
        conn.execute("INSERT OR IGNORE INTO seen_urls (url, first_seen) VALUES (?, ?)", (job.url, now))
        cur = conn.execute(
            """INSERT OR IGNORE INTO jobs
               (url, title, snippet, description, company, location, source, salary_min, salary_max,
                salary_currency, employment_type, posted_at, remote, fingerprint, status, fetched_at,
                description_length, run_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job.url, job.title.strip(), job.snippet or None, job.description or None, job.company or None,
                job.location or None, job.source, job.salary_min, job.salary_max, job.salary_currency,
                job.employment_type, job.posted_at, None if job.remote is None else int(job.remote), fp,
                STATUS_NEW, now, len(job.description or ""), run_id,
            ),
        )
        if cur.rowcount:
            new_ids.append(cur.lastrowid)
    return new_ids, dup_url, dup_fp


def get_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_jobs(conn: sqlite3.Connection, ids: Iterable[int]) -> list[dict[str, Any]]:
    ids = list(ids)
    if not ids:
        return []
    out: list[dict[str, Any]] = []
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        q = ",".join("?" * len(chunk))
        out.extend(dict(r) for r in conn.execute(f"SELECT * FROM jobs WHERE id IN ({q})", chunk))  # noqa: S608
    return out


def jobs_with_status(conn: sqlite3.Connection, status: str, limit: int | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM jobs WHERE status = ? ORDER BY fetched_at ASC"
    params: list[Any] = [status]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]


def update_job(conn: sqlite3.Connection, job_id: int, **fields: Any) -> None:
    bad = set(fields) - JOB_COLUMNS
    if bad:
        raise ValueError(f"unknown job columns: {bad}")
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE jobs SET {sets} WHERE id = ?", [*fields.values(), job_id])  # noqa: S608


def set_user_action(conn: sqlite3.Connection, job_id: int, action: str) -> None:
    update_job(conn, job_id, user_action=action, user_action_at=now_iso())


def queued_since(conn: sqlite3.Connection, since_iso: str) -> list[dict[str, Any]]:
    """Jobs shortlisted by scoring that happened after ``since_iso`` — including carry-over jobs
    fetched in an earlier run, which a ``run_id`` filter would miss."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM jobs WHERE scored_at >= ? AND status IN ('queued','docs_generated') "
            "ORDER BY fit_score DESC, id ASC",
            (since_iso,),
        )
    ]


# ---------------------------------------------------------------------------
# Expiry — postings that are too old to still be open, or whose page is gone
# ---------------------------------------------------------------------------

def active_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Shortlisted jobs you have not acted on yet."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM jobs WHERE status IN ('queued','docs_generated') AND user_action IS NULL ORDER BY id")]


def mark_expired(conn: sqlite3.Connection, job_id: int, reason: str) -> None:
    update_job(conn, job_id, status=STATUS_EXPIRED, skip_reason=f"expired: {reason}", processed_at=now_iso())


def stale_by_age(conn: sqlite3.Connection, posted_max_days: int, fetched_max_days: int,
                 today: datetime | None = None) -> list[tuple[int, str]]:
    """(job_id, reason) for active jobs older than the limits. Uses posted_at when the source gave one,
    otherwise the day we first saw the job."""
    now = today or datetime.now(UTC)
    out: list[tuple[int, str]] = []
    for j in active_jobs(conn):
        posted = (j.get("posted_at") or "")[:10]
        try:
            posted_dt = datetime.fromisoformat(posted).replace(tzinfo=UTC) if posted else None
        except ValueError:
            posted_dt = None
        if posted_dt is not None:
            age = (now - posted_dt).days
            if age > posted_max_days:
                out.append((j["id"], f"posted {posted}, {age} days ago (limit {posted_max_days})"))
            continue
        fetched_dt = datetime.fromisoformat(j["fetched_at"])
        if fetched_dt.tzinfo is None:
            fetched_dt = fetched_dt.replace(tzinfo=UTC)
        age = (now - fetched_dt).days
        if age > fetched_max_days:
            out.append((j["id"], f"no posting date; first seen {j['fetched_at'][:10]}, {age} days ago (limit {fetched_max_days})"))
    return out


def jobs_for_link_check(conn: sqlite3.Connection, limit: int, min_age_days: int = 3,
                        recheck_after_days: int = 7) -> list[dict[str, Any]]:
    """Active jobs whose URL is worth (re)checking: seen at least ``min_age_days`` ago and not checked in the
    last ``recheck_after_days``. Never-checked first, then the longest-unchecked."""
    return [dict(r) for r in conn.execute(
        """SELECT * FROM jobs
           WHERE status IN ('queued','docs_generated') AND user_action IS NULL
             AND julianday('now') - julianday(fetched_at) >= ?
             AND (link_checked_at IS NULL OR julianday('now') - julianday(link_checked_at) >= ?)
           ORDER BY link_checked_at IS NOT NULL, link_checked_at, id
           LIMIT ?""",
        (min_age_days, recheck_after_days, limit),
    )]


# ---------------------------------------------------------------------------
# ATS cache
# ---------------------------------------------------------------------------

def get_ats_cache(conn: sqlite3.Connection, slug: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM company_ats_cache WHERE company_slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def set_ats_cache(conn: sqlite3.Connection, slug: str, name: str, ats_type: str, base_url: str) -> None:
    conn.execute(
        """INSERT INTO company_ats_cache (company_slug, company_name, ats_type, ats_base_url, last_probed, probe_count)
           VALUES (?,?,?,?,?,1)
           ON CONFLICT(company_slug) DO UPDATE SET company_name=excluded.company_name, ats_type=excluded.ats_type,
             ats_base_url=excluded.ats_base_url, last_probed=excluded.last_probed, probe_count=probe_count+1""",
        (slug, name, ats_type, base_url, now_iso()),
    )


# ---------------------------------------------------------------------------
# Runs / pipeline state / commands
# ---------------------------------------------------------------------------

def start_run(conn: sqlite3.Connection, dry_run: bool) -> int:
    cur = conn.execute("INSERT INTO runs (started_at, dry_run) VALUES (?, ?)", (now_iso(), int(dry_run)))
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, status: str, **counts: Any) -> None:
    allowed = {"fetched", "new_jobs", "prefiltered", "scored", "queued", "skipped", "docs", "errors", "llm_calls", "notes",
               "expired"}
    fields = {k: v for k, v in counts.items() if k in allowed}
    sets = ", ".join(f"{k} = ?" for k in fields)
    sql = "UPDATE runs SET finished_at = ?, status = ?" + (", " + sets if sets else "") + " WHERE id = ?"  # noqa: S608
    conn.execute(sql, [now_iso(), status, *fields.values(), run_id])  # noqa: S608


def record_source_run(conn: sqlite3.Connection, run_id: int, source: str, started_at: str, duration_s: float,
                      fetched: int, new_jobs: int, error: str | None) -> None:
    conn.execute(
        "INSERT INTO source_runs (run_id, source, started_at, duration_s, fetched, new_jobs, error) VALUES (?,?,?,?,?,?,?)",
        (run_id, source, started_at, round(duration_s, 1), fetched, new_jobs, error),
    )


def get_pipeline_state(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM pipeline_state WHERE id = 1").fetchone()
    return dict(row) if row else {"status": "idle"}


def set_pipeline_state(conn: sqlite3.Connection, **fields: Any) -> None:
    allowed = {"status", "started_at", "current_phase", "jobs_total", "jobs_processed", "log_tail", "command", "run_id", "pid"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE pipeline_state SET {sets} WHERE id = 1", list(fields.values()))  # noqa: S608


def consume_abort(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT command FROM pipeline_state WHERE id = 1").fetchone()
    if row and row["command"] == "abort":
        conn.execute("UPDATE pipeline_state SET command = NULL WHERE id = 1")
        conn.commit()
        return True
    return False


def enqueue_command(conn: sqlite3.Connection, command: str, arg: str | None = None) -> int:
    cur = conn.execute("INSERT INTO commands (command, arg, created_at) VALUES (?,?,?)", (command, arg, now_iso()))
    return int(cur.lastrowid)


def claim_next_command(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM commands WHERE status = 'pending' ORDER BY id LIMIT 1").fetchone()
    if not row:
        return None
    conn.execute("UPDATE commands SET status = 'running', started_at = ? WHERE id = ?", (now_iso(), row["id"]))
    conn.commit()
    return dict(row)


def finish_command(conn: sqlite3.Connection, command_id: int, status: str, result: str = "") -> None:
    conn.execute(
        "UPDATE commands SET status = ?, finished_at = ?, result = ? WHERE id = ?",
        (status, now_iso(), result[:2000], command_id),
    )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    by_status = {r["status"]: r["c"] for r in conn.execute("SELECT status, COUNT(*) c FROM jobs GROUP BY status")}
    by_source = {r["source"]: r["c"] for r in conn.execute("SELECT source, COUNT(*) c FROM jobs GROUP BY source ORDER BY c DESC")}
    by_action = {r["user_action"]: r["c"] for r in conn.execute(
        "SELECT user_action, COUNT(*) c FROM jobs WHERE user_action IS NOT NULL GROUP BY user_action")}
    scores = {r["fit_score"]: r["c"] for r in conn.execute(
        "SELECT fit_score, COUNT(*) c FROM jobs WHERE fit_score IS NOT NULL GROUP BY fit_score ORDER BY fit_score")}
    last_runs = [dict(r) for r in conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 10")]
    total = conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
    return {"total": total, "by_status": by_status, "by_source": by_source, "by_user_action": by_action,
            "score_distribution": scores, "last_runs": last_runs}


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)

import sqlite3

from autojob import db as D
from autojob.models import RawJob


def make_v1(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE NOT NULL, title TEXT, snippet TEXT,
          company TEXT, fit_score INTEGER, fit_reasoning TEXT, strengths TEXT, gaps TEXT, skip_reason TEXT,
          status TEXT DEFAULT 'new', fetched_at TEXT NOT NULL, processed_at TEXT, output_folder TEXT,
          description TEXT, low_confidence INTEGER DEFAULT 0, description_length INTEGER);
        CREATE TABLE seen_urls (url TEXT PRIMARY KEY, first_seen TEXT NOT NULL);
        CREATE TABLE job_fingerprints (id INTEGER PRIMARY KEY, url TEXT, title_normalized TEXT, company_normalized TEXT,
          source TEXT, created_at TEXT, UNIQUE(url));
        CREATE TABLE pipeline_state (id INTEGER PRIMARY KEY DEFAULT 1, status TEXT DEFAULT 'idle', started_at TEXT,
          current_phase TEXT, jobs_total INTEGER, jobs_processed INTEGER, log_tail TEXT, command TEXT);
        INSERT INTO pipeline_state (id, status) VALUES (1, 'idle');
        INSERT INTO jobs (url, title, company, status, fetched_at, fit_score) VALUES
          ('https://linkedin.com/jobs/view/1', 'Ops Coordinator', 'Acme', 'docs_generated', '2026-05-01T00:00:00', 8),
          ('https://www.adzuna.ca/details/2', 'Ops Analyst', 'Beta', 'skipped', '2026-05-02T00:00:00', 3);
        """
    )
    conn.commit()
    conn.close()


def test_migrates_v1_and_inserts(tmp_path):
    p = tmp_path / "a.db"
    make_v1(p)
    D.init_db(p)
    with D.db(p) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == D.SCHEMA_VERSION
        rows = {r["url"]: dict(r) for r in conn.execute("SELECT * FROM jobs")}
        assert rows["https://linkedin.com/jobs/view/1"]["source"] == "boards"
        assert rows["https://linkedin.com/jobs/view/1"]["fingerprint"] == "ops coordinator|acme"
        assert rows["https://linkedin.com/jobs/view/1"]["docs_generated_at"] is not None
        assert conn.execute("SELECT COUNT(*) FROM seen_urls").fetchone()[0] == 2
        # duplicates: same url → skipped; same title+company under new url → fingerprint dup
        new_ids, dup_url, dup_fp = D.insert_jobs(conn, [
            RawJob(url="https://linkedin.com/jobs/view/1", title="Ops Coordinator", company="Acme", source="boards"),
            RawJob(url="https://other.example/x", title="Ops Coordinator", company="Acme Inc", source="serper"),
            RawJob(url="https://other.example/y", title="RevOps Associate", company="Gamma", source="serper"),
        ], run_id=None)
        assert (len(new_ids), dup_url, dup_fp) == (1, 1, 1)
        D.update_job(conn, new_ids[0], status=D.STATUS_QUEUED, fit_score=7)
        assert D.get_job(conn, new_ids[0])["status"] == "queued"
    # second init is a no-op
    D.init_db(p)


def test_fresh_db_and_commands(tmp_path):
    p = tmp_path / "b.db"
    D.init_db(p)
    with D.db(p) as conn:
        cid = D.enqueue_command(conn, "docs", "42")
        cmd = D.claim_next_command(conn)
        assert cmd["id"] == cid and cmd["command"] == "docs"
        assert D.claim_next_command(conn) is None
        D.finish_command(conn, cid, "done", "ok")
        rid = D.start_run(conn, dry_run=False)
        D.finish_run(conn, rid, "done", fetched=10, new_jobs=3)
        assert D.stats(conn)["last_runs"][0]["fetched"] == 10
        D.set_pipeline_state(conn, command="abort")
        assert D.consume_abort(conn) is True
        assert D.consume_abort(conn) is False

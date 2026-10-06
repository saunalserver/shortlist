"""pipeline.score_jobs with a worker pool: results land in the DB from the main thread, budget stops cleanly."""
import threading
import time

from autojob import db as D
from autojob import pipeline as P
from autojob.llm import LLMBudgetExceeded
from autojob.models import RawJob


class _Settings:
    def __init__(self, workers):
        self.cfg = {"scoring.min_score_to_queue": 7, "scoring.workers": workers}

    def get(self, key, default=None):
        return self.cfg.get(key, default)


class _LLM:
    calls = 0
    last_model = "fake-model"


def _setup(tmp_path, n):
    p = tmp_path / "t.db"
    D.init_db(p)
    conn = D.connect(p)
    ids, _, _ = D.insert_jobs(conn, [RawJob(url=f"https://x/{i}", title=f"Ops {i}", company=f"C{i}")
                                     for i in range(n)], None)
    conn.commit()
    return conn, D.get_jobs(conn, ids)


def test_parallel_scoring_writes_all_results(tmp_path, monkeypatch):
    main = threading.get_ident()
    seen_threads = set()

    class FakeScorer:
        def __init__(self, settings, llm):
            pass

        def score(self, job):
            seen_threads.add(threading.get_ident())
            time.sleep(0.05)
            n = int(job["title"].split()[-1])
            return {"fit_score": 8 if n % 2 else 3, "skip": False, "strengths": [], "gaps": [],
                    "low_confidence": False, "one_liner": "x", "model": None}

    monkeypatch.setattr("autojob.scorer.Scorer", FakeScorer)
    conn, jobs = _setup(tmp_path, 12)
    orig_update = D.update_job

    def guarded_update(c, jid, **f):
        assert threading.get_ident() == main   # DB writes only on the main thread
        return orig_update(c, jid, **f)

    monkeypatch.setattr(D, "update_job", guarded_update)
    summary = P.RunSummary(run_id=1, dry_run=False)
    queued = P.score_jobs(_Settings(4), conn, jobs, _LLM(), summary)
    assert summary.scored == 12 and len(queued) == 6 and summary.skipped == 6
    assert len(seen_threads) > 1 and main not in seen_threads
    rows = conn.execute("SELECT status, scorer_model FROM jobs").fetchall()
    assert {r["status"] for r in rows} == {D.STATUS_QUEUED, D.STATUS_SKIPPED}
    assert {r["scorer_model"] for r in rows} == {"fake-model"}


def test_llm_circuit_breaker_stops_the_run(tmp_path, monkeypatch):
    """Report 03 Bug 5: a hard-down provider must not grind the run to the 8 h systemd cap."""
    class DeadScorer:
        def __init__(self, settings, llm):
            pass

        def score(self, job):
            return None

    monkeypatch.setattr("autojob.scorer.Scorer", DeadScorer)
    conn, jobs = _setup(tmp_path, 30)
    summary = P.RunSummary(run_id=1, dry_run=False)
    P.score_jobs(_Settings(2), conn, jobs, _LLM(), summary)
    assert 10 <= summary.scored <= 12     # stops at the 10th consecutive failure (+ in-flight batch remainder)
    assert summary.errors == summary.scored
    assert "circuit breaker" in summary.notes
    new = conn.execute("SELECT count(*) FROM jobs WHERE status = ?", (D.STATUS_NEW,)).fetchone()[0]
    assert new == 30 - summary.scored     # unstarted jobs stay 'new' for the next run
    assert summary.as_row()["notes"] == summary.notes   # lands in the runs row


def test_budget_stops_and_leaves_rest_new(tmp_path, monkeypatch):
    lock = threading.Lock()
    state = {"n": 0}

    class FakeScorer:
        def __init__(self, settings, llm):
            pass

        def score(self, job):
            with lock:
                state["n"] += 1
                n = state["n"]
            if n > 3:
                raise LLMBudgetExceeded("budget")
            return {"fit_score": 8, "skip": False, "strengths": [], "gaps": [], "low_confidence": False}

    monkeypatch.setattr("autojob.scorer.Scorer", FakeScorer)
    conn, jobs = _setup(tmp_path, 20)
    summary = P.RunSummary(run_id=1, dry_run=False)
    P.score_jobs(_Settings(2), conn, jobs, _LLM(), summary)
    assert summary.scored == 3
    new = conn.execute("SELECT count(*) FROM jobs WHERE status = ?", (D.STATUS_NEW,)).fetchone()[0]
    assert new == 17

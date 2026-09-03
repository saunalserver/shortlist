from datetime import UTC, datetime

from autojob import db as D
from autojob.expire import expire
from autojob.models import RawJob


def _seed(conn, **overrides):
    url = overrides.pop("url")
    j = RawJob(url=url, title="Ops Coordinator", company=f"Co {url[-3:]}", source="boards", **overrides)
    ids, _, _ = D.insert_jobs(conn, [j], run_id=1)
    return ids[0]


def test_age_rules(tmp_path):
    p = tmp_path / "e.db"
    D.init_db(p)
    with D.db(p) as conn:
        old_posted = _seed(conn, url="https://x/1", posted_at="2026-06-01")
        fresh_posted = _seed(conn, url="https://x/2", posted_at="2026-08-30")
        no_date = _seed(conn, url="https://x/3")
        for jid in (old_posted, fresh_posted, no_date):
            D.update_job(conn, jid, status=D.STATUS_QUEUED, fit_score=7)
        conn.execute("UPDATE jobs SET fetched_at = '2026-06-15T00:00:00+00:00' WHERE id = ?", (no_date,))
        acted = _seed(conn, url="https://x/4", posted_at="2026-05-01")
        D.update_job(conn, acted, status=D.STATUS_DOCS, user_action="applied")
        stale = D.stale_by_age(conn, 30, 45, today=datetime(2026, 9, 2, tzinfo=UTC))
        assert {i for i, _ in stale} == {old_posted, no_date}   # acted-on jobs are never expired
        res = expire(conn, posted_max_days=30, fetched_max_days=45, link_checks=0)
        assert set(res["ids"]) == {old_posted, no_date}
        assert D.get_job(conn, old_posted)["status"] == "expired"
        assert D.get_job(conn, old_posted)["skip_reason"].startswith("expired: posted 2026-06-01")
        assert D.get_job(conn, fresh_posted)["status"] == "queued"
        assert D.active_jobs(conn) and all(j["id"] == fresh_posted for j in D.active_jobs(conn))


def test_digest_uses_scoring_time_not_run_id(tmp_path):
    p = tmp_path / "d.db"
    D.init_db(p)
    with D.db(p) as conn:
        carried = _seed(conn, url="https://x/old")          # fetched by run 1, scored later
        D.update_job(conn, carried, status=D.STATUS_QUEUED, fit_score=8, scored_at="2026-09-02T14:30:00+00:00")
        earlier = _seed(conn, url="https://x/earlier")
        D.update_job(conn, earlier, status=D.STATUS_QUEUED, fit_score=9, scored_at="2026-09-01T10:00:00+00:00")
        got = [j["id"] for j in D.queued_since(conn, "2026-09-02T14:02:00+00:00")]
        assert got == [carried]


def test_dead_phrase_detection(monkeypatch):
    from autojob import expire as E

    class R:
        def __init__(self, status, text=""):
            self.status_code, self.text = status, text

    monkeypatch.setattr(E.requests, "get", lambda *a, **k: R(200, "<html><body><p>No longer accepting applications</p></body></html>"))
    assert E.check_link("https://linkedin.com/jobs/view/1") == "page says 'no longer accepting applications'"
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: R(404))
    assert E.check_link("https://x/gone") == "HTTP 404"
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: R(403))
    assert E.check_link("https://x/blocked") is None
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: R(200, "<html>Apply now for Operations Coordinator</html>"))
    assert E.check_link("https://x/alive") is None

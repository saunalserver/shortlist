"""Digest build (2026-10-06): acted jobs excluded, stale/low-conf demoted, ranked by expected apply."""
from datetime import UTC, datetime

from autojob import db as D
from autojob.models import RawJob
from autojob.notify import digest_jobs, send_digest

CFG = {
    "source_priors": {"serper": 1.0, "boards": 0.5},
    "freshness_bonus": 1.0,
    "low_confidence_penalty": 1.0,
}


def _job(i, source="serper", score=8, scored_at="2026-10-01T00:00:00+00:00", company="Acme", low_conf=0):
    return {"id": i, "source": source, "fit_score": score, "scored_at": scored_at, "company": company,
            "low_confidence": low_conf, "title": f"Job {i}", "url": f"https://x/{i}", "status": "queued"}


def test_digest_ranking_composes_score_prior_freshness_and_company_history():
    today = datetime(2026, 10, 2, tzinfo=UTC)
    jobs = [
        _job(1, source="boards", score=8),                   # 8 + 0.5 + 1.0           = 9.5
        _job(2, score=7),                                    # 7 + 1.0 + 1.0           = 9.0
        _job(5, score=8, company="Sailor Health"),           # 8 + 1.0 + 1.0 − 2       = 8.0
        _job(6, score=8, scored_at="2026-09-28T00:00:00+00:00"),  # 4 d old: 8 + 1.0 + 0.91 = 9.91
    ]
    out = digest_jobs(jobs, CFG, {"sailor health": 2}, today=today)
    assert [j["id"] for j in out] == [6, 1, 2, 5]
    assert out[0]["_rank"] == 9.91


def test_digest_demotes_stale_and_low_confidence():
    today = datetime(2026, 10, 2, tzinfo=UTC)
    jobs = [
        _job(3, scored_at="2026-09-10T00:00:00+00:00"),      # 22 d old → out of the digest
        _job(4, low_conf=1),                                 # 0/41 lifetime applies → out
        _job(7),                                             # stays
    ]
    out = digest_jobs(jobs, CFG, {}, today=today)
    assert [j["id"] for j in out] == [7]


def test_queued_since_skips_acted_jobs(tmp_path):
    p = tmp_path / "d.db"
    D.init_db(p)
    with D.db(p) as conn:
        ids, _, _ = D.insert_jobs(conn, [
            RawJob(url="https://x/1", title="Ops", company="A", source="boards"),
            RawJob(url="https://x/2", title="Ops", company="B", source="boards"),
            RawJob(url="https://x/3", title="Ops", company="C", source="boards"),
        ], run_id=1)
        for jid in ids:
            D.update_job(conn, jid, status=D.STATUS_QUEUED, fit_score=8, scored_at="2026-10-01T00:00:00+00:00")
        D.update_job(conn, ids[1], user_action="dismissed")
        D.update_job(conn, ids[2], user_action="applied")
        got = [j["id"] for j in D.queued_since(conn, "2026-09-30T00:00:00+00:00")]
        assert got == [ids[0]]


def test_digest_carries_expiring_soon_line(monkeypatch):
    class _S:
        def get(self, key, default=None):
            return None

    sent = []
    monkeypatch.setattr("autojob.notify._send", lambda settings, text: sent.append(text) or True)
    send_digest(_S(), {"started_at": "2026-10-02T07:00:00+00:00", "fetched": 10}, [_job(1)], expiring_soon=4)
    assert "4 pending jobs retire within 3 days" in sent[0]

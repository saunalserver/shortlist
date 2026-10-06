"""Run-step fixes from the 2026-10-06 review: zero-fetch surfacing, the docs abort guard, blocklist wiring."""
import pytest

from autojob import db as D
from autojob import pipeline as P
from autojob import sources as S
from autojob.models import RawJob


class _Settings:
    """Minimal Settings stub: nested get() + the secrets LLM() needs at construction."""

    class _Secrets:
        llm_api_key = "test"
        llm_base_url = "https://example/v1"

    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self.secrets = self._Secrets()

    def get(self, key, default=None):
        node = self.cfg
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def test_fetch_all_flags_zero_row_sources(tmp_path, monkeypatch):
    p = tmp_path / "z.db"
    D.init_db(p)
    conn = D.connect(p)
    monkeypatch.setattr(S, "enabled", lambda settings, only: ["dead", "alive"])

    class _Src:
        def __init__(self, rows):
            self.rows = rows

        def fetch(self, settings):
            return self.rows

    monkeypatch.setattr(S, "load", lambda name: _Src(
        [] if name == "dead" else [RawJob(url=f"https://x/{name}", title="Ops", company="C", source=name)]))
    summary = P.RunSummary(run_id=1, dry_run=False)
    jobs = P.fetch_all(_Settings(), conn, 1, None, summary)
    assert len(jobs) == 1
    assert summary.per_source["dead"]["error"].startswith("warning: 0 rows fetched")
    assert summary.per_source["alive"]["error"] is None


def test_docs_command_does_not_consume_the_run_abort_flag(tmp_path, monkeypatch):
    p = tmp_path / "a.db"
    D.init_db(p)
    conn = D.connect(p)
    ids, _, _ = D.insert_jobs(conn, [RawJob(url="https://x/1", title="Ops", company="C", source="boards")], None)
    conn.commit()
    D.set_pipeline_state(conn, command="abort")
    conn.commit()

    class FakeGen:
        def __init__(self, settings, llm):
            pass

        def generate(self, job):
            return ("out", True, True)

    monkeypatch.setattr("autojob.docs.DocGenerator", FakeGen)
    settings = _Settings({"scoring": {"docs_models": [{"name": "m"}]}})
    assert P.generate_docs_for(settings, conn, ids) == 1          # standalone docs: flag untouched
    assert D.get_pipeline_state(conn)["command"] == "abort"
    with pytest.raises(P.Aborted):                                  # run context: abort is honoured
        P.generate_docs_for(settings, conn, ids, summary=P.RunSummary(run_id=1, dry_run=False))
    assert D.get_pipeline_state(conn)["command"] is None


def test_pipeline_prefilter_applies_company_blocklist(tmp_path):
    p = tmp_path / "b.db"
    D.init_db(p)
    conn = D.connect(p)
    ids, _, _ = D.insert_jobs(conn, [
        RawJob(url="https://x/1", title="Operations Coordinator", company="Acme Inc", source="boards"),
        RawJob(url="https://x/2", title="Operations Coordinator", company="Beta", source="boards"),
    ], run_id=1)
    conn.commit()
    summary = P.RunSummary(run_id=1, dry_run=False)
    keep = P.prefilter(_Settings({"prefilter": {"title_allow_phrases": [], "title_exclude_words": [],
                                                "title_exclude_phrases": []}}),
                       conn, D.get_jobs(conn, ids), summary, {"acme"})
    assert summary.prefiltered == 1
    assert D.get_job(conn, ids[0])["prefilter_reason"] == "company_blocklist"
    assert [j["id"] for j in keep] == [ids[1]]

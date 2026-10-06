"""Scorer v2: the model extracts facts, compute_v2 turns them into score + skip."""
import pytest

from autojob.scorer import compute_v2
from autojob.settings import get_settings


@pytest.fixture(scope="module")
def w():
    return get_settings().get("scoring.v2")


def facts(**kw):
    base = dict(role_family="operations", duties_match=2, seniority="junior", employer_type="smb",
                location_ok=True, employment_type="unknown")
    base.update(kw)
    return base


def test_target_role_scores_high(w):
    r = compute_v2(facts(duties_match=3, signals=["early_career", "tool_overlap"], employer_type="startup"), w)
    assert r["fit_score"] >= 9 and not r["skip"]


def test_retail_manager_is_skipped_low(w):
    r = compute_v2(facts(role_family="retail_hospitality", duties_match=0, seniority="manager",
                         people_manager=True, employer_type="enterprise"), w)
    assert r["skip"] and r["fit_score"] <= 2


@pytest.mark.parametrize("kw,why", [
    (dict(location_ok=False, location_note="must reside in France"), "location"),
    (dict(employment_type="contract"), "employment type"),
    (dict(seniority="senior"), "seniority"),
    (dict(years_required=6), "years"),
    (dict(employer_type="agency_or_hidden"), "agency"),
    (dict(careers_index=True), "careers index"),
    (dict(citizenship_required=True), "citizenship"),
    (dict(role_family="software_engineering"), "role family"),
])
def test_disqualifiers_cap_at_3(w, kw, why):
    r = compute_v2(facts(duties_match=3, signals=["automation_ai", "tool_overlap"], **kw), w)
    assert r["skip"] and r["fit_score"] <= 3 and why in r["skip_reason"]


def test_adjacent_with_gaps_stays_below_queue(w):
    r = compute_v2(facts(role_family="customer_success", duties_match=1, seniority="mid", years_required=3,
                         missing_must_haves=["3+ years CSM"], employer_type="startup"), w)
    assert r["fit_score"] < 7 and not r["skip"]


def test_signals_are_capped_and_unknown_ignored(w):
    few = compute_v2(facts(signals=["automation_ai", "tool_overlap"]), w)["fit_score"]
    many = compute_v2(facts(signals=["automation_ai", "tool_overlap", "ownership", "made_up"]), w)["fit_score"]
    assert few == many


def test_garbage_facts_do_not_crash(w):
    r = compute_v2({"duties_match": "lots", "years_required": "three", "signals": None}, w)
    assert 1 <= r["fit_score"] <= 10 and "breakdown" not in r["skip_reason"] if r["skip_reason"] else True


def test_manager_title_not_penalized(w):
    """2026-10-06: manager seniority and people_manager cost nothing — 4 of 18 applies are manager-titled
    (Operations Manager BC, Client Success Manager, Associate PM, PM; report 01 §2.5)."""
    base = facts(role_family="operations", duties_match=2, seniority="mid", employer_type="smb")
    mgr = facts(role_family="operations", duties_match=2, seniority="manager", people_manager=True,
                employer_type="smb")
    assert compute_v2(mgr, w)["fit_score"] == compute_v2(base, w)["fit_score"]


@pytest.mark.parametrize("fam", ["implementation_onboarding", "project_program_coord"])
def test_coordinator_families_demoted_to_adjacent(w, fam):
    """2026-10-06: coordination/onboarding families score one tier below a true target family — offline
    labels carry 1:12 and 0:8 apply:top-band-dismissal ratios for them (reports 01 §5, 06 §2.4)."""
    demoted = compute_v2(facts(role_family=fam, duties_match=3, seniority="junior"), w)["fit_score"]
    target = compute_v2(facts(role_family="operations", duties_match=3, seniority="junior"), w)["fit_score"]
    assert demoted == target - 2 and demoted < target


def test_near_perfect_fit_reaches_ceiling(w):
    """The 9–10 band must be reachable: the duties/systems-building profile of the applies
    (d3 + early-career + tools + startup) still tops out at 9–10 after the 2026-10-06 retune."""
    r = compute_v2(facts(role_family="automation_ai_ops", duties_match=3, seniority="junior", years_required=1,
                         employer_type="startup", signals=["automation_ai", "tool_overlap", "early_career"]), w)
    assert r["fit_score"] >= 9 and not r["skip"]


def test_v2_score_facts_populated_end_to_end(tmp_path):
    """2026-10-06 flip to scoring.version 2: the real Scorer (v2 prompt, fake LLM client) returns facts,
    and pipeline.score_jobs' real write path lands them in the DB score_facts column."""
    import json

    from autojob import db as D
    from autojob import pipeline as P
    from autojob.llm import LLM
    from autojob.models import RawJob
    from autojob.settings import get_settings

    model_facts = {"company": "Acme", "role_family": "operations", "duties_match": 3, "seniority": "junior",
                   "people_manager": False, "years_required": 1, "missing_must_haves": [],
                   "employment_type": "permanent", "work_mode": "remote", "location_ok": True,
                   "citizenship_required": False, "employer_type": "startup", "careers_index": False,
                   "signals": ["automation_ai", "tool_overlap"], "strengths": [], "gaps": [],
                   "one_liner": "Ops automation at a startup, 1+ yrs, builds n8n workflows"}

    llm = LLM("key", "https://example.invalid/v1/", [{"name": "m", "rpm": 1000}])

    class FakeCompletions:
        def create(self, **kwargs):
            content = json.dumps(model_facts)
            msg = type("M", (), {"content": content})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    llm.client = type("Client", (), {"chat": type("Chat", (), {"completions": FakeCompletions()})()})()

    real = get_settings()

    class S:
        def prompt(self, name):
            return real.prompt(name)

        def candidate_profile(self):
            return real.candidate_profile()

        def get(self, key, default=None):
            return {"scoring.version": 2, "scoring.min_score_to_queue": 7, "scoring.workers": 1}.get(key, default)

    p = tmp_path / "t.db"
    D.init_db(p)
    conn = D.connect(p)
    ids, _, _ = D.insert_jobs(conn, [RawJob(url="https://x/1", title="Ops Analyst", company="Acme",
                                            description="d" * 300)], None)
    conn.commit()
    summary = P.RunSummary(run_id=1, dry_run=False)
    P.score_jobs(S(), conn, D.get_jobs(conn, ids), llm, summary)

    row = conn.execute("SELECT fit_score, status, score_facts FROM jobs WHERE id = ?", (ids[0],)).fetchone()
    payload = json.loads(row["score_facts"])
    assert row["fit_score"] >= 7 and row["status"] == "queued"      # 6+1+1+1+2+1 = 12 → 10
    assert payload["role_family"] == "operations" and "breakdown" in payload
    assert summary.scored == 1 and summary.skipped == 0

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

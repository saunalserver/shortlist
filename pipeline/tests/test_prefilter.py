import yaml

from autojob.prefilter import location_reason, prefilter_reason
from autojob.settings import ROOT

CFG = yaml.safe_load((ROOT / "config" / "search.yaml").read_text())["prefilter"]


def job(**kw):
    base = {"title": "Operations Coordinator", "location": "Vancouver, BC", "employment_type": None, "remote": None}
    base.update(kw)
    return base


def test_remote_ca_is_remote_canada_not_california():
    # report 05 §2 Bug A: boards' Canada remote_only pass writes exactly "Remote, CA" — the trailing CA
    # parsed as California, all 281 such rows prefiltered, 0 ever scored.
    assert prefilter_reason(job(location="Remote, CA", remote=1), CFG) is None
    assert location_reason("Remote, CA", CFG["location"], remote=1) is None
    assert location_reason("Remote - CA", CFG["location"], remote=1) is None
    # genuine US cities with CA keep dying
    assert location_reason("San Francisco, CA", CFG["location"]) == "location: san francisco (US)"
    assert location_reason("Los Angeles, CA", CFG["location"]) == "location: los angeles (US)"
    assert location_reason("Fresno, CA", CFG["location"]) == "location: United States"


def test_source_remote_flag_counts_as_remote_wording():
    # report 05 §2 Bug B: `remote is True` never fired on SQLite's int 1 — 504 remote-flagged jobs died on
    # deny-city rules (toronto 191, montréal 59, calgary 52 …)
    assert location_reason("Toronto, ON", CFG["location"], remote=1) is None
    assert location_reason("Toronto, ON", CFG["location"], remote=0) == "location: toronto"
    assert prefilter_reason(job(location="Montréal, QC", remote=1), CFG) is None


def test_supply_chain_title_carve_out():
    # planner/buyer/scheduler pass when paired with a supply-chain function word (title_sc_* in search.yaml)
    assert prefilter_reason(job(title="Supply Chain Buyer II"), CFG) is None
    assert prefilter_reason(job(title="Demand Planner"), CFG) is None
    assert prefilter_reason(job(title="Logistics Coordinator (Scheduler)"), CFG) is None
    # without the function word they stay dead
    assert prefilter_reason(job(title="Media Buyer"), CFG) == "title: buyer"
    assert prefilter_reason(job(title="Appointment Scheduler"), CFG) == "title: scheduler"
    assert prefilter_reason(job(title="Production Planner"), CFG) == "title: planner"
    # the carve-out lifts only those three words — every other title rule still applies
    assert prefilter_reason(job(title="Senior Demand Planner"), CFG) == "title: senior"
    assert prefilter_reason(job(title="Supply Chain Buyer (Contract)"), CFG) == "title: (contract"


def test_company_blocklist_skips_repeat_offenders():
    assert prefilter_reason(job(company="Acme Inc"), CFG, {"acme"}) == "company_blocklist"
    assert prefilter_reason(job(company="Acme Inc"), CFG, set()) is None
    assert prefilter_reason(job(company="Other Co"), CFG, {"acme"}) is None


def test_keeps_target_role():
    assert prefilter_reason(job(), CFG) is None


def test_rejects_senior_and_lead_as_whole_words_only():
    assert prefilter_reason(job(title="Senior Operations Analyst"), CFG) == "title: senior"
    assert prefilter_reason(job(title="Team Lead, Ops"), CFG) == "title: lead"
    assert prefilter_reason(job(title="Leadership Program Coordinator"), CFG) is None
    assert prefilter_reason(job(title="Sr. Operations Manager"), CFG) == "title: sr"


def test_rejects_engineering_phrases():
    assert prefilter_reason(job(title="Software Engineer, Operations Tooling"), CFG) == "title: software engineer"
    assert prefilter_reason(job(title="Operations Engineer"), CFG) is None  # ambiguous → LLM decides


def test_rejects_internships_by_type_and_title():
    assert prefilter_reason(job(employment_type="Internship"), CFG) == "employment type: internship"
    assert prefilter_reason(job(title="Operations Intern"), CFG) == "title: intern"


def test_location_rules():
    assert prefilter_reason(job(location="Toronto, ON"), CFG) == "location: toronto"
    assert prefilter_reason(job(location="Toronto, ON (Remote)"), CFG) is None
    assert prefilter_reason(job(location="Austin, TX"), CFG) == "location: austin (US)"
    assert prefilter_reason(job(location="New York, NY 10001"), CFG) == "location: United States"
    assert prefilter_reason(job(location="Boise, ID"), CFG) == "location: United States"
    assert prefilter_reason(job(location="Canada"), CFG) is None
    assert prefilter_reason(job(location="Burnaby, British Columbia"), CFG) is None
    assert prefilter_reason(job(location=""), CFG) is None
    assert prefilter_reason(job(location="Québec, QC"), CFG) == "location: québec"
    # 2026-09-02 rule + 2026-10-06 owner call: US-remote is now in policy when doable from Canada —
    # a remote US-based job passes (see test_us_remote_policy_2026_10_06); on-site US still drops
    assert prefilter_reason(job(location="Seattle, WA", remote=True), CFG) is None
    assert prefilter_reason(job(location="Remote (Canada or US)", remote=True), CFG) is None
    assert prefilter_reason(job(location="San Francisco, New York, Remote in US"), CFG) is None
    assert prefilter_reason(job(location="US-Remote"), CFG) is None
    assert prefilter_reason(job(location="Chicago, US-Remote, Canada-Remote"), CFG) is None


def test_us_remote_policy_2026_10_06():
    """Owner call 2026-10-06: US-remote acceptable when doable from Canada. Remote US-based jobs pass to
    the scorer (which DQs explicit US-residency pins); on-site/hybrid US and residency restrictions die."""
    lr = CFG["location"]
    # remote US-based → pass
    assert location_reason("Seattle, WA", lr, remote=1) is None
    assert location_reason("Austin, TX (Remote)", lr) is None
    assert location_reason("Remote, US", lr, remote=1) is None
    assert location_reason("Remote - United States", lr, remote=1) is None
    assert location_reason("US-Remote", lr) is None
    # on-site / hybrid US → still dead
    assert location_reason("Austin, TX", lr) == "location: austin (US)"
    assert location_reason("New York, NY 10001", lr) == "location: United States"
    assert location_reason("San Francisco, CA", lr) == "location: san francisco (US)"
    assert location_reason("New York, NY (Hybrid)", lr, remote=1) is not None
    # explicit US-residency restrictions → dead even when remote
    assert location_reason("Remote - US only", lr, remote=1) == "location: US only"
    assert location_reason("Remote (US residents only)", lr, remote=1) == "location: US only"
    assert location_reason("Remote — must reside in the US", lr, remote=1) == "location: US only"


def test_employer_block_words_2026_10_06():
    """Owner call 2026-10-06: hard-block edu/gov/nonprofit employers (0/18 applies vs 17/290 dismissals).
    Word list validated against all 18 applied companies — zero matches."""
    assert prefilter_reason(job(company="University of British Columbia"), CFG) == "employer: university"
    assert prefilter_reason(job(company="Trinity Western University"), CFG) == "employer: university"
    assert prefilter_reason(job(company="Canadian Cancer Society"), CFG) == "employer: society"
    assert prefilter_reason(job(company="Fraser Health Authority"), CFG) == "employer: health authority"
    assert prefilter_reason(job(company="City of Surrey"), CFG) == "employer: city of"
    assert prefilter_reason(job(company="College of Physicians and Surgeons of BC"), CFG) == "employer: college"
    # none of the applied-class employers trips a word
    assert prefilter_reason(job(company="ZayZoon"), CFG) is None
    assert prefilter_reason(job(company="7shifts"), CFG) is None
    assert prefilter_reason(job(company="Super.com"), CFG) is None
    assert prefilter_reason(job(company=None), CFG) is None
    assert prefilter_reason(job(company=""), CFG) is None

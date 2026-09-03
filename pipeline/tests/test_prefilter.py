import yaml

from autojob.prefilter import prefilter_reason
from autojob.settings import ROOT

CFG = yaml.safe_load((ROOT / "config" / "search.yaml").read_text())["prefilter"]


def job(**kw):
    base = {"title": "Operations Coordinator", "location": "Vancouver, BC", "employment_type": None, "remote": None}
    base.update(kw)
    return base


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
    # since 2026-09-02 a "remote" job pinned to a US city is dropped too — "Seattle, WA (remote)" means US-remote
    assert prefilter_reason(job(location="Seattle, WA", remote=True), CFG) == "location: seattle (US)"
    assert prefilter_reason(job(location="Remote (Canada or US)", remote=True), CFG) is None
    assert prefilter_reason(job(location="San Francisco, New York, Remote in US"), CFG) == "location: US only"
    assert prefilter_reason(job(location="US-Remote"), CFG) == "location: US only"
    assert prefilter_reason(job(location="Chicago, US-Remote, Canada-Remote"), CFG) is None

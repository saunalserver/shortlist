"""Location rules added 2026-09-02: deny-city beats "Canada", US checks apply to remote jobs, foreign regions."""
import yaml

from autojob.prefilter import location_reason, prefilter_reason
from autojob.settings import ROOT

CFG = yaml.safe_load((ROOT / "config" / "search.yaml").read_text())["prefilter"]
LOC = CFG["location"]


def job(**kw):
    base = {"title": "Operations Coordinator", "location": "Vancouver, BC", "employment_type": None, "remote": None}
    base.update(kw)
    return base


def test_other_canadian_city_is_dropped_even_when_canada_is_named():
    assert location_reason("Toronto, Ontario, Canada", LOC) == "location: toronto"
    assert location_reason("Edmonton, Alberta, Canada", LOC) == "location: edmonton"
    assert location_reason("Etobicoke, Ontario, Canada", LOC) is None   # not in deny list → LLM decides


def test_multi_city_posting_naming_vancouver_is_kept():
    assert location_reason("Vancouver, BC / Toronto, ON", LOC) is None
    assert location_reason("Toronto, ON (Remote)", LOC) is None


def test_remote_jobs_still_get_the_us_check():
    assert location_reason("Remote - Houston", LOC, remote=True) == "location: houston (US)"
    assert location_reason("Chicago, IL, Flexible / Remote", LOC, remote=True) == "location: chicago (US)"
    assert location_reason("HQ - San Francisco, CA, New York", LOC) == "location: United States"
    assert location_reason("Remote - United States", LOC, remote=True) == "location: US only"
    assert location_reason("Remote - Canada; Remote - US", LOC, remote=True) is None
    assert location_reason("Canada, United States", LOC, remote=True) is None
    assert location_reason("Remote NA", LOC, remote=True) is None


def test_foreign_regions_are_dropped_unless_canada_or_global():
    assert location_reason("Remote - EMEA", LOC, remote=True) == "location: emea"
    assert location_reason("Flexible / Remote, New Delhi, India", LOC, remote=True) in ("location: new delhi", "location: india")
    assert location_reason("Australia, Canada, India, United Kingdom", LOC, remote=True) is None
    assert location_reason("Worldwide", LOC, remote=True) is None
    assert location_reason("London, UK", LOC) in ("location: london", "location: uk")


def test_prefilter_passes_remote_flag_through():
    assert prefilter_reason(job(location="Remote - Houston", remote=True), CFG) == "location: houston (US)"
    assert prefilter_reason(job(location="Remote", remote=True), CFG) is None
    assert prefilter_reason(job(location="", remote=None), CFG) is None


def test_new_title_and_type_rules():
    assert prefilter_reason(job(title="Part Time Key Holder"), CFG) == "title: part time"
    assert prefilter_reason(job(title="People Operations Specialist"), CFG) == "title: people operations"
    assert prefilter_reason(job(title="Talent Development Coordinator - Temporary (4 months)"), CFG) == "title: talent"
    assert prefilter_reason(job(title="Data Partner - Philosophy - Remote - Asia"), CFG) == "title: data partner"
    assert prefilter_reason(job(title="Sales Representative"), CFG) == "title: representative"
    assert prefilter_reason(job(employment_type="Part-time"), CFG) == "employment type: part-time"
    # things that must still reach the LLM
    for t in ("Operations Analyst", "Chief of Staff", "Business Operations Engineer", "Special Projects",
              "Human Data Manager, New Grad", "Technical Solutions Engineer", "Revenue Operations Analyst II"):
        assert prefilter_reason(job(title=t), CFG) is None, t


def test_old_postings_are_dropped_before_scoring():
    from datetime import UTC, datetime

    from autojob.prefilter import posted_age_days
    assert posted_age_days("2026-07-05", datetime(2026, 9, 2, tzinfo=UTC)) == 59
    assert posted_age_days(None) is None and posted_age_days("soon") is None
    assert prefilter_reason(job(posted_at="2026-01-01"), CFG).startswith("posted: 2026-01-01")
    assert prefilter_reason(job(posted_at=datetime.now(UTC).strftime("%Y-%m-%d")), CFG) is None


def test_exclusion_words_match_plurals_and_bc_noise():
    assert prefilter_reason(job(title="Warehouse Drivers Needed"), CFG) in ("title: warehouse", "title: drivers")
    assert prefilter_reason(job(title="Registered Nurses - ICU"), CFG) == "title: nurses"
    assert prefilter_reason(job(title="Project Coordinator - Civil Construction"), CFG) in ("title: civil", "title: construction")
    assert prefilter_reason(job(title="Site Coordinator"), CFG) == "title: site"
    assert prefilter_reason(job(title="PLC Automation Specialist"), CFG) == "title: plc"
    assert prefilter_reason(job(title="Building Automation Controls Specialist"), CFG) in ("title: controls", "title: building automation")
    assert prefilter_reason(job(title="Leadership Program Coordinator"), CFG) is None
    assert prefilter_reason(job(title="Website Operations Coordinator"), CFG) is None
    assert prefilter_reason(job(title="Onboarding Specialist"), CFG) is None


def test_full_time_permanent_only():
    assert prefilter_reason(job(title="Operations Coordinator (Contract)"), CFG) == "title: (contract"
    assert prefilter_reason(job(title="Operations Analyst - 12 Month Contract"), CFG) == "title: month contract"
    assert prefilter_reason(job(title="Coordinator, Maternity Leave Coverage"), CFG) in ("title: maternity leave", "title: leave coverage")
    assert prefilter_reason(job(employment_type="Contractor"), CFG) == "employment type: contract"
    assert prefilter_reason(job(employment_type="Full-time"), CFG) is None
    assert prefilter_reason(job(title="Contracts Administrator"), CFG) is None   # a role about contracts, not a contract role

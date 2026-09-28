"""Parsing tests for remoterocketship + workingnomads (no network)."""
import json

from autojob.sources import remoterocketship as rr
from autojob.sources import workingnomads as wn


def _rr_job(**over):
    j = {
        "roleTitle": "Account Operations Specialist", "url": "https://career.avenga.com/jobs/8463698-x?utm_source=rr",
        "company": {"name": "Avenga"}, "location": "Bulgaria", "locationCountries": None, "locationType": "remote",
        "employmentType": "full-time", "isEntryLevel": False, "isJunior": True, "isMidLevel": False,
        "isSenior": False, "isLead": False, "created_at": "2026-09-28T14:42:12.202+00:00",
        "twoLineJobDescriptionSummary": "Coordinating client requests and billing.", "dateDeleted": None,
    }
    j.update(over)
    return j


def test_rr_parse_page_and_to_raw():
    payload = {"props": {"pageProps": {"initialJobOpenings": [_rr_job()], "initialTotalJobCount": 1}}}
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></html>'
    openings, total = rr.parse_page(html)
    assert len(openings) == 1 and total == 1
    job = rr.to_raw(openings[0])
    assert job.title == "Account Operations Specialist" and job.company == "Avenga"
    assert job.url == "https://career.avenga.com/jobs/8463698-x"          # tracking param stripped
    assert job.location == "Remote — Bulgaria" and job.remote is True
    assert job.posted_at == "2026-09-28" and job.source == "remoterocketship"
    assert rr.parse_page("<html>no data</html>") == ([], None)


def test_rr_filters_seniority_type_and_multi_country_location():
    assert rr.to_raw(_rr_job(isSenior=True, isJunior=False)) is None
    assert rr.to_raw(_rr_job(isSenior=True, isMidLevel=True, isJunior=False)) is not None   # mixed label kept
    assert rr.to_raw(_rr_job(employmentType="contract")) is None
    assert rr.to_raw(_rr_job(locationType="hybrid")) is None
    multi = rr.to_raw(_rr_job(location="Europe", locationCountries=["France", "Germany", "Spain"]))
    assert multi.location == "Remote — Europe (France, Germany, Spain)"


def test_rr_residency_policy():
    assert not rr.open_to_canada(_rr_job(location="Bulgaria"))
    assert not rr.open_to_canada(_rr_job(location="Europe", locationCountries=["France", "Germany"]))
    assert rr.open_to_canada(_rr_job(location="United States", locationCountries=["United States", "Canada"]))
    assert rr.open_to_canada(_rr_job(location="Worldwide"))
    assert rr.open_to_canada(_rr_job(location="North America"))
    assert rr.open_to_canada(_rr_job(location=None, locationCountries=None))    # no info → kept


def test_rr_pages_from_config():
    cfg = {"regions": ["europe"], "title_slugs": ["operations-specialist", "sales-operations"],
           "extra_pages": ["worldwide/jobs/operations-specialist"]}
    assert rr._pages(cfg) == ["europe/jobs/operations-specialist", "europe/jobs/sales-operations",
                              "worldwide/jobs/operations-specialist"]


def _wn(**over):
    s = {"title": "Sales Operations Analyst", "company": "Canonical", "position_type": "ft",
         "experience_level": "MID_LEVEL", "locations": ["EMEA", "North America"], "expired": False,
         "apply_url": "https://job-boards.greenhouse.io/canonical/jobs/5924435", "slug": "sales-ops-canonical",
         "description": "<p>Own the sales ops stack.</p>", "pub_date": "2026-09-23T10:00:00-04:00"}
    s.update(over)
    return s


def test_wn_residency_policy():
    assert wn.open_to_canada(["Canada", "USA"])
    assert wn.open_to_canada(["USA, Canada"])
    assert wn.open_to_canada(["EMEA", "Latin America", "North America"])
    assert wn.open_to_canada(["Anywhere"])
    assert wn.open_to_canada(["Americas"])
    assert wn.open_to_canada([])                      # unspecified remote → kept
    assert not wn.open_to_canada(["EMEA"])            # explicit residency restriction
    assert not wn.open_to_canada(["Europe"])
    assert not wn.open_to_canada(["Spain", "Portugal"])
    assert not wn.open_to_canada(["USA"])
    assert not wn.open_to_canada(["Latin America"])


def test_wn_to_raw_and_filters():
    job = wn.to_raw(_wn(), {"SENIOR_LEVEL"})
    assert job.url == "https://job-boards.greenhouse.io/canonical/jobs/5924435"
    assert job.location == "Remote — EMEA, North America" and job.remote is True
    assert "Own the sales ops stack." in job.description and job.posted_at == "2026-09-23"
    assert job.employment_type == "full-time"
    assert wn.to_raw(_wn(position_type="fr"), set()) is None
    assert wn.to_raw(_wn(experience_level="SENIOR_LEVEL"), {"SENIOR_LEVEL"}) is None
    assert wn.to_raw(_wn(expired=True), set()) is None
    fallback = wn.to_raw(_wn(apply_url=""), set())
    assert fallback.url == "https://workingnomads.com/jobs/sales-ops-canonical"


def test_wn_query_body():
    body = wn.build_query(["operations analyst", "revenue operations"], 7, 300)
    should = body["query"]["bool"]["should"]
    assert {"match_phrase": {"title": "operations analyst"}} in should
    assert body["query"]["bool"]["filter"][0]["range"]["pub_date"]["gte"] == "now-7d"

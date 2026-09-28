"""Parsing rules for the jobs.workable.com search and Welcome to the Jungle (Algolia) sources."""
from autojob.sources.workable_search import parse_job, residence_allows_us
from autojob.sources.wttj import parse_hit


def _wk(**over):
    row = {
        "title": "Revenue Operations Analyst", "workplace": "remote", "employmentType": "Full-time",
        "url": "https://jobs.workable.com/view/abc/remote-revenue-operations-analyst?utm_source=x",
        "locations": ["TELECOMMUTE", "Ottawa, Ontario, Canada"],
        "location": {"city": "Ottawa", "subregion": "Ontario", "countryName": "Canada"},
        "created": "2026-09-25T13:38:52.282Z", "company": {"title": "Nuvei", "website": "https://nuvei.com"},
        "description": "<p>Own the <b>RevOps</b> stack.</p>", "requirementsSection": "<ul><li>SQL</li></ul>",
    }
    row.update(over)
    return row


def test_workable_remote_row():
    job, why = parse_job(_wk(), {"location": "Canada", "workplace": "remote"})
    assert why is None and job is not None
    assert job.remote is True
    assert job.location == "Remote (office: Ottawa, Canada)"
    assert job.company == "Nuvei" and job.posted_at == "2026-09-25"
    assert "RevOps" in job.description and "SQL" in job.description


def test_workable_pass_rules():
    remote_pc = {"location": "Canada", "workplace": "remote"}
    assert parse_job(_wk(workplace="hybrid"), remote_pc) == (None, "not remote")
    assert parse_job(_wk(employmentType="Contract"), remote_pc) == (None, "employment type")
    assert parse_job(_wk(employmentType=""), remote_pc)[0] is not None          # untagged = kept
    uae = _wk(location={"city": "Dubai", "countryName": "United Arab Emirates"}, locations=["TELECOMMUTE"])
    assert parse_job(uae, {"location": "Europe", "workplace": "remote", "europe_only": True}) == (None, "outside Europe")
    ro = _wk(location={"city": "Bucharest", "countryName": "Romania"}, locations=["TELECOMMUTE"])
    assert parse_job(ro, {"location": "Europe", "workplace": "remote", "europe_only": True})[0].location \
        == "Remote (office: Bucharest, Romania)"


def test_workable_vancouver_onsite_and_residency():
    van = _wk(workplace="hybrid", location={"city": "Burnaby", "subregion": "British Columbia", "countryName": "Canada"})
    job, _ = parse_job(van, {"location": "Vancouver", "country": "Canada"})
    assert job.location == "Burnaby, British Columbia, Canada (hybrid)" and job.remote is False
    wa = _wk(workplace="on_site", location={"city": "Vancouver", "subregion": "Washington", "countryName": "United States"})
    assert parse_job(wa, {"location": "Vancouver", "country": "Canada"}) == (None, "wrong country")
    # explicit residency list without an open / Canadian entry → dropped
    assert residence_allows_us(["TELECOMMUTE", "Paris, France"])
    assert residence_allows_us([])
    assert not residence_allows_us(["Paris, France", "Lyon, France"])
    assert parse_job(_wk(locations=["Berlin, Germany"]), {"location": "Europe", "workplace": "remote"}) \
        == (None, "residence restricted")


def _hit(**over):
    h = {
        "name": "Revenue Strategy & Operations Manager", "contract_type": "full_time", "remote": "fulltime",
        "experience_level_minimum": 2.0, "slug": "revenue-strategy-operations-manager_paris_360LE_KxRDqo3",
        "organization": {"name": "360Learning", "slug": "360learning"},
        "offices": [{"city": "Paris", "state": "Ile-de-France", "country": "France", "country_code": "FR"}],
        "summary": "Partner to Sales leadership.", "key_missions": ["Own forecasting", "Run QBRs"],
        "profile": "2+ years in RevOps.", "published_at": "2026-09-27T10:00:00Z",
        "salary_minimum": 50000.0, "salary_maximum": 60000.0, "salary_currency": "EUR", "salary_period": "yearly",
    }
    h.update(over)
    return h


def test_wttj_remote_hit():
    job, why = parse_hit(_hit(), {"country_codes": ["FR"]}, 3)
    assert why is None
    assert job.url.endswith("/fr/companies/360learning/jobs/revenue-strategy-operations-manager_paris_360LE_KxRDqo3")
    assert job.location == "Remote (office: Paris, France)" and job.remote is True
    assert "Own forecasting" in job.description and "2+ years" in job.description
    assert (job.salary_min, job.salary_currency, job.posted_at) == (50000.0, "EUR", "2026-09-27")


def test_wttj_filters_and_office_choice():
    assert parse_hit(_hit(contract_type="internship")) == (None, "contract")
    assert parse_hit(_hit(experience_level_minimum=5.0), None, 3) == (None, "experience")
    assert parse_hit(_hit(experience_level_minimum=None), None, 3)[0] is not None
    assert parse_hit(_hit(salary_period="monthly"))[0].salary_min is None
    offices = [{"city": "Toronto", "country": "Canada", "country_code": "CA"},
               {"city": "Vancouver", "state": "British Columbia", "country": "Canada", "country_code": "CA"}]
    job, _ = parse_hit(_hit(remote="partial", offices=offices), {"office_cities": ["Vancouver"], "country_codes": ["CA"]})
    assert job.location == "Vancouver, British Columbia, Canada (hybrid)" and job.remote is False

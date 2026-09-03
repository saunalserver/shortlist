from datetime import UTC, datetime

from autojob.sources.eluta import ago_to_date, parse_results
from autojob.sources.serper import _clean_title, _location_from_url
from autojob.sources.workday import posted_on_to_date

TODAY = datetime(2026, 9, 2, 12, tzinfo=UTC)


def test_workday_posted_on():
    assert posted_on_to_date("Posted Today", TODAY) == "2026-09-02"
    assert posted_on_to_date("Posted Yesterday", TODAY) == "2026-09-01"
    assert posted_on_to_date("Posted 8 Days Ago", TODAY) == "2026-08-25"
    assert posted_on_to_date("Posted 30+ Days Ago", TODAY) == "2026-08-03"
    assert posted_on_to_date(None) is None


def test_eluta_ago_and_parsing():
    assert ago_to_date("16 hours ago", TODAY) == "2026-09-01"
    assert ago_to_date("3 days ago", TODAY) == "2026-08-30"
    html = """<div class="organic-job odd" data-url="spl/operations-coordinator-abc?imo=12">
      <h2 class="title"><a class="lk-job-title" data-url="spl/operations-coordinator-abc?imo=12" href="#!" title="Operations Coordinator">Operations Coordinator</a>
      <span class="position-salary"><span>$52,000</span> - <span>$60,000</span></span></h2>
      <a class="employer lk-employer" href="#!" title="See all jobs at Leavitt">Leavitt Machinery</a>
      <span class="location"><span>Langley, BC</span></span>
      <span class="description">... support the development of service processes</span>
      <a class="lk lastseen" href="#!">8 hours ago</a></div>"""
    rows = parse_results(html)
    assert rows == [{"url": "https://www.eluta.ca/spl/operations-coordinator-abc", "title": "Operations Coordinator",
                     "company": "Leavitt Machinery", "location": "Langley, BC", "salary": "$52,000 - $60,000",
                     "snippet": "... support the development of service processes", "ago": "8 hours ago"}]


def test_serper_title_and_workday_location():
    assert _clean_title("Operations Associate - Careers - Myworkdayjobs.com") == "Operations Associate"
    assert _clean_title("Project Coordinator - CMiC - Workable Jobs") == "Project Coordinator - CMiC"
    assert _clean_title("Ops Analyst | LinkedIn") == "Ops Analyst"
    assert _location_from_url("https://ubc.wd10.myworkdayjobs.com/en-US/ubcstaffjobs/job/UBC-Vancouver-Campus---Vancouver-BC-Canada/Coordinator_JR25862") \
        == "UBC Vancouver Campus, Vancouver BC Canada"
    assert _location_from_url("https://jobs.lever.co/acme/123") == ""


def test_scraper_rejects_bot_walls(monkeypatch):
    from autojob import scraper

    class R:
        status_code = 200
        text = "<html><body><main>" + "We hate to have to ask this, but... are you a human? You've arrived at this page because we're getting just a few too many unusual requests from you. " * 6 + "</main></body></html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(scraper, "_pace", lambda: None)
    assert scraper.scrape("https://example.com/job/1") is None
    assert scraper.scrape("https://www.eluta.ca/spl/x") is None   # blocked host, no request made

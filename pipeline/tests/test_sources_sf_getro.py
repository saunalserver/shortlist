from autojob.sources.getro import canada_keep, remote_open_to_vancouver, to_raw
from autojob.sources.successfactors import location_keep, parse_feed, split_title

FEED = """<?xml version="1.0" encoding="UTF-8" ?><rss version='2.0'><channel>
<title>ICBC - Custom Search (operations)</title>
<item><title><![CDATA[Business Analytics Consultant (Burnaby, British Columbia, Canada)]]></title>
<description><![CDATA[<p>Own the <b>reporting</b> &amp; dashboards.</p>]]></description>
<pubDate>Tue, 22 Sep 2026 0:00:00 GMT</pubDate>
<link>https://careers.icbc.com/job/Burnaby-Business-Analytics-Consultant-Brit/606363717/?feedId=null&amp;utm_source=J2WRSS</link>
</item>
<item><title><![CDATA[Project Manager I (Vancouver, British Columbia (BC), Canada, V6A 4K6)]]></title>
<description><![CDATA[x]]></description><pubDate>Fri, 25 Sep 2026 0:00:00 GMT</pubDate>
<link>https://jobs.vancouver.ca/job/Vancouver-Project-Manager-I/1/</link></item>
</channel></rss>"""


def test_successfactors_parse_feed():
    rows = parse_feed(FEED)
    assert [r["title"] for r in rows] == ["Business Analytics Consultant", "Project Manager I"]
    assert rows[0]["location"] == "Burnaby, British Columbia, Canada"
    assert rows[0]["posted_at"] == "2026-09-22"
    assert "reporting" in rows[0]["description"] and "&amp;" not in rows[0]["description"]
    assert rows[1]["location"] == "Vancouver, British Columbia (BC), Canada, V6A 4K6"


def test_successfactors_split_title_and_location():
    assert split_title("Analyst (Mortgage) (Toronto, ON, CA, M5H3R3)") == ("Analyst (Mortgage)", "Toronto, ON, CA, M5H3R3")
    assert split_title("No location here") == ("No location here", "")
    assert location_keep("Coquitlam, British Columbia, Canada") == (True, False)
    assert location_keep("Remote within, BC, CA") == (True, True)
    assert location_keep("Toronto, ON, CA, M5H 1H1") == (False, False)
    assert location_keep("Remote, San Jose, CA, US")[0] is False     # CA = California here
    assert location_keep("Hybrid - Kamloops or Vancouver, BC, CA")[0] is True


def test_getro_remote_residency_rule():
    assert remote_open_to_vancouver(["Remote"]) is True
    assert remote_open_to_vancouver([]) is True
    assert remote_open_to_vancouver(["Canada", "Remote"]) is True
    assert remote_open_to_vancouver(["Europe", "Canada", "Remote"]) is True
    assert remote_open_to_vancouver(["Worldwide"]) is True
    assert remote_open_to_vancouver(["Germany", "Remote"]) is False     # pinned to a country = residency
    assert remote_open_to_vancouver(["Europe", "Remote"]) is False
    assert remote_open_to_vancouver(["United States", "Remote"]) is False


def test_getro_canada_pass_and_to_raw():
    local = {"work_mode": "on_site", "locations": ["Vancouver, BC, Canada"]}
    assert canada_keep(local) == (True, False)
    assert canada_keep({"work_mode": "remote", "locations": ["Ontario, Canada", "Remote"]}) == (True, True)
    assert canada_keep({"work_mode": "on_site", "locations": ["Toronto, ON, Canada"]})[0] is False
    job = {"title": " Associate, Brokerage Operations ", "url": "https://jobs.ashbyhq.com/ws/abc?utm_source=getro",
           "organization": {"name": "Wealthsimple"}, "work_mode": "remote", "locations": ["Canada"],
           "created_at": 1790258421, "compensation_amount_min_cents": 6000000,
           "compensation_amount_max_cents": 8000000, "compensation_period": "year", "compensation_currency": "CAD"}
    raw = to_raw(job, "Inovia", True)
    assert raw.title == "Associate, Brokerage Operations" and raw.company == "Wealthsimple"
    assert raw.location == "Canada (remote)" and raw.remote is True
    assert raw.salary_min == 60000 and raw.salary_currency == "CAD"
    assert raw.url == "https://jobs.ashbyhq.com/ws/abc"
    assert raw.posted_at and raw.posted_at.startswith("2026-")

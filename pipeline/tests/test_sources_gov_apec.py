from autojob.sources.apec import FULL_REMOTE, build_body, to_raw
from autojob.sources.bcps import clean_location, clean_title, parse_rows
from autojob.sources.gcjobs import parse_detail, parse_results, total_pages

BCPS_HTML = """<table id="jobSearchResultsGrid_table"><thead><tr><th>Ministry</th></tr></thead><tbody>
<tr><td>Destination BC Corp.</td><td>125916</td>
<td><a href="/hr/ats/Posting/view/125916"> <span>FO 21R - Financial Analyst** Work Options amended**</span></a></td>
<td>GEU</td><td>Hybrid</td><td> Vancouver, BC, CA V6B 0N8<br /></td><td>9/14/2026</td><td>9/28/2026</td></tr>
<tr><td>Children &amp; Family Development</td><td>126072</td>
<td><a href="/hr/ats/Posting/view/126072"> <span>CLK 09 - Team Assistant - Amended</span></a></td>
<td>GEU</td><td>Hybrid</td>
<td> Multiple Locations, BC, CA (Primary) Vancouver, BC, CA V6B 0N8 Victoria, BC, CA V9B 6X2<br /></td>
<td>9/24/2026</td><td>10/8/2026</td></tr>
</tbody></table>"""


def test_bcps_rows_titles_locations():
    rows = parse_rows(BCPS_HTML)
    assert [r["title"] for r in rows] == ["Financial Analyst", "Team Assistant"]
    assert rows[0]["url"] == "https://bcpublicservice.hua.hrsmart.com/hr/ats/Posting/view/125916"
    assert rows[0]["posted_at"] == "2026-09-14"
    assert rows[0]["work_option"] == "Hybrid"
    assert rows[1]["location"] == "Vancouver, BC; Victoria, BC"


def test_bcps_clean_title_and_location():
    assert clean_title("SPO-CP 24R (Growth) - Child Protection Worker - Closing date extended") \
        == "Child Protection Worker"
    assert clean_title("PARALGL 18 + 10% - Paralegal LSB") == "Paralegal LSB"
    assert clean_title("Legislative Assembly - Server") == "Legislative Assembly - Server"  # lowercase → not a code
    assert clean_title("MGR 18R - Store Manager, Cannabis Operations_AMENDED") == "Store Manager, Cannabis Operations"
    assert clean_location("100 Mile House, BC, CA V0K 2E0 Burnaby, BC, CA V3J 1N3") == "100 Mile House, BC; Burnaby, BC"


GC_RESULTS = """<p>… <a href="page2440?requestedPage=20&amp;fromPage=1&amp;tab=1&amp;log=false">20</a> of 21 [Next]</p>
<ol class="posterInfo"><li class="searchResult">
 <div><strong><a href="/psrs-srfp/applicant/page1800?poster=2449750">Bilingual Senior Analyst, Information Business Systems</a></strong></div>
 <div class="tableTable"><div class="tableRow">
  <div class="tableCell">Closing date: 2026-09-28<br/>Canada Mortgage and Housing Corporation<br/>Various Locations<br/></div>
  <div class="tableCell">Bilingual - imperative<br/>$73,555 to $91,944</div>
 </div></div></li>
<li class="searchResult">
 <div><strong><a href="/psrs-srfp/applicant/page1800?poster=2461400">Audit Professional</a></strong></div>
 <div class="tableTable"><div class="tableRow">
  <div class="tableCell">Closing date: 2026-09-30<br/>Office of the Auditor General of Canada
   <br/>- Audit Branch<br/>Edmonton (Alberta), Vancouver (British Columbia)<br/></div>
  <div class="tableCell">English essential<br/>$81,970 to $95,295 ((Plus allowances.))</div>
 </div></div></li></ol>"""


def test_gcjobs_results():
    rows = parse_results(GC_RESULTS)
    assert total_pages(GC_RESULTS) == 21
    assert rows[0] == {"poster": "2449750", "title": "Bilingual Senior Analyst, Information Business Systems",
                       "organization": "Canada Mortgage and Housing Corporation", "location": "Various Locations",
                       "closing": "2026-09-28", "language": "Bilingual - imperative", "salary": "$73,555 to $91,944"}
    assert rows[1]["organization"] == "Office of the Auditor General of Canada - Audit Branch"
    assert rows[1]["location"] == "Edmonton (Alberta), Vancouver (British Columbia)"
    assert rows[1]["salary"] == "$81,970 to $95,295"


def test_gcjobs_detail_external_and_internal():
    external = """<main><h1>You will leave the GC Jobs Web site</h1><p>…</p>
      <a href="https://careers.bankofcanada.ca/job/Ottawa-Analyst/606072017/">Analyst</a></main>"""
    assert parse_detail(external) == ("https://careers.bankofcanada.ca/job/Ottawa-Analyst/606072017/", "")
    internal = """<main><h1>Clinical Social Worker</h1><p>Who can apply</p><p>Persons residing in Canada</p>
      <p>Date modified:</p><p>2026-09-15</p></main>"""
    url, desc = parse_detail(internal)
    assert url is None and "Persons residing in Canada" in desc and "Date modified" not in desc


def test_apec_body_and_mapping():
    body = build_body("", 100, 200)
    assert body["typesContrat"] == ["101888"] and body["typesTeletravail"] == [FULL_REMOTE] == ["20767"]
    assert body["pagination"] == {"range": 100, "startIndex": 200}
    job = to_raw({"numeroOffre": "179497558W", "intitule": "Gestionnaire finance et opérations F/H",
                  "nomCommercial": "Actual", "lieuTexte": "Paris 08 - 75", "salaireTexte": "45 - 50 k€ brut annuel",
                  "texteOffre": "Vous pilotez <b>les opérations</b> financières…",
                  "datePublication": "2026-09-23T10:00:00.000+0000"})
    assert job.url == "https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/179497558W"
    assert job.remote is True and job.employment_type == "CDI" and job.posted_at == "2026-09-23"
    assert job.location == "Télétravail total — France (Paris 08 - 75)"
    assert "les opérations financières" in job.description and "<b>" not in job.description

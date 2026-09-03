# Sources

Yield numbers are from the runs on 2026-09-01/02 (Vancouver, operations-role queries). "New" depends on how many days you have been running.

| Source | Auth | Cost | Typical fetch | Notes |
|---|---|---|---|---|
| `boards` (LinkedIn + Indeed via python-jobspy) | none | ~3 min | ~200 | Indeed gives full descriptions; LinkedIn descriptions fetched per job. ZipRecruiter (403) and Glassdoor (location parse) don't work from a server. |
| `adzuna` | free key | 3 s | ~40 | Canada-wide aggregator. Since 2026-09-02 queries match the **title only** (`match: title`): 39 relevant results instead of ~530 mostly-irrelevant ones. Descriptions are truncated to 500 chars by Adzuna. |
| `workday` | none | ~70 s | ~75 | Big Vancouver employers that post only on their own Workday board (UBC, Aritzia, STEMCELL…). Public `wday/cxs` API; add tenants in `search.yaml` (`tenant`, `wd`, `site` from the careers URL). Full descriptions, one request per new relevant posting (`max_details_per_run`). |
| `eluta` | none | 13 s | ~60 | Canadian aggregator of employer career sites, Vancouver radius. Search results are HTML; the job pages are bot-walled, so scoring uses the search snippet only (low confidence). Catches health authorities, biotech and engineering firms the big boards miss. |
| `himalayas` | none | 30 s | ~450 | Remote jobs with `country=CA` + worldwide. Sends a plain User-Agent (browser UAs get 403). Full descriptions. Postings labelled Director/Executive/VP/C-Level are dropped at the source (`skip_seniority`). |
| `ats_companies` | none | ~2 min | 100–600 | ~150 Greenhouse/Lever/Ashby boards from `search.yaml`. Title must contain an ops phrase; location must be Canada/remote-not-elsewhere. Run `autojob companies verify` monthly. |
| `jobicy` | none | 4 s | ~80 | Remote, `geo=canada`, by industry tag. |
| `jooble` | free key (lifetime cap) | 1 s | ~60 | Only `max_queries` searches per run to conserve the cap. Snippets only. |
| `themuse` | none | 1 s | ~60 | Filtered to entry/mid levels; includes non-Canadian remote roles the LLM then skips. |
| `weworkremotely` | none | 1 s | ~50 | Category RSS feeds. Mostly senior/US; prefilter handles most. |
| `remoteok` | none | 1 s | ~30 | Single public feed filtered by tag. |
| `jobbank` (Government of Canada) | none | 13 s | ~25 | Location parameter is ignored by the site; province codes are dropped by the prefilter. Low yield. |
| `serper` (Google) | free key, 2,500 credits total | 10 s | ~20 | `queries_per_run` searches rotate through the `plan` (ATS domains, Wellfound, city). Every ATS-domain search is scoped `(Vancouver OR Canada)` — unscoped, 98 of 99 results were US/India Workday postings. Workday result URLs are parsed for location. Free accounts: `num` ≤ 10, no `gl`/`hl`. |
| `remotive` | none | 1 s | ~20 | The public API now returns a small recent slice regardless of parameters. |
| `yc` | none | 2–5 min | 5–30 | Discovers "hiring" YC companies via their Algolia index, detects each company's ATS (cached 30 days incl. negatives), pulls ops roles. `max_new_probes_per_run` bounds the cost. |

Ideas not implemented: Wellfound (no API, blocks scraping), WorkBC (JavaScript app), Glassdoor/ZipRecruiter (bot-walled), Workable widget API (needs a slug list — `autojob companies probe` could be extended), bcjobs.ca (404 to scripted requests), Working Nomads (developer-heavy), more Workday tenants (lululemon, Teck, BCIT, SFU, TELUS — the tenants exist but their site names were not found; open the careers page, copy the path segment after `myworkdayjobs.com/`).

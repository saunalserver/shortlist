# Sources

Yield numbers are from the runs on 2026-09-01/02 (Vancouver, operations-role queries). "New" depends on how many days you have been running. **Disabled 2026-09-07 as dead** (0–1 queued across 4 days, audit in `AUDIT-sourcing-expansion-2026-09-07.md`): jobbank, remotive, remoteok, jobicy, themuse, yc.

| Source | Auth | Cost | Typical fetch | Notes |
|---|---|---|---|---|
| `boards` (LinkedIn + Indeed via python-jobspy) | none | ~3 min | ~200–500 | Indeed gives full descriptions; LinkedIn descriptions fetched per job. ZipRecruiter and Glassdoor added 2026-09-07 — both silently return 0 from this server IP; audit 2026-09-21, kill if still 0. |
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
| `serper` (Google) | free key, 2,500 credits total | 10 s | ~480 | `queries_per_run` 48 searches rotate through the 9-step `plan` (ATS domains, Wellfound, T-Net, city) — ~96 credits/day at 2 runs/day; spend tracked in the `meta` table (serper.dev has no balance API, `/api/credit` 404s). Every ATS-domain search is scoped `(Vancouver OR Canada)` — unscoped, 98 of 99 results were US/India Workday postings. Free accounts: `num` ≤ 10, no `gl`/`hl`. |
| `amazon` (amazon.jobs public JSON) | none | 2 s | ~170/day | Full descriptions + basic quals inline → zero scrape cost. Vancouver-scoped (added 2026-09-07). |
| `hn` (Who-is-hiring via Algolia) | none | 2 s | ~45/month | Monthly thread; titles are rough but scoring copes. |
| `remotive` | none | 1 s | ~20 | The public API now returns a small recent slice regardless of parameters. |
| `yc` | none | 2–5 min | 5–30 | Discovers "hiring" YC companies via their Algolia index, detects each company's ATS (cached 30 days incl. negatives), pulls ops roles. `max_new_probes_per_run` bounds the cost. |

Ideas not implemented: Wellfound direct (no API, blocks scraping — covered via serper plan step instead), WorkBC (JavaScript app), Glassdoor/ZipRecruiter scraping (bot-walled — jobspy attempt live but returns 0), Workable widget API (needs a slug list — `autojob companies probe` could be extended), bcjobs.ca (404 to scripted requests), Working Nomads (developer-heavy), more Workday tenants (lululemon, Teck, BCIT, SFU, TELUS — the tenants exist but their site names were not found; open the careers page, copy the path segment after `myworkdayjobs.com/`). T-Net (bctechnology.com) direct fetch is Cloudflare-walled; covered by a serper `site:` plan step instead.

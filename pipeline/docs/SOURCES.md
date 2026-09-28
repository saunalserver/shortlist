# Sources

Yield numbers are from the runs on 2026-09-01/02 (Vancouver, operations-role queries). "New" depends on how many days you have been running. **Disabled 2026-09-07 as dead** (0–1 queued across 4 days, audit in `AUDIT-sourcing-expansion-2026-09-07.md`): jobbank, remotive, remoteok, jobicy, themuse, yc.

| Source | Auth | Cost | Typical fetch | Notes |
|---|---|---|---|---|
| `boards` (LinkedIn + Indeed via python-jobspy) | none | ~4–6 min | ~250–700 | Indeed gives full descriptions; LinkedIn descriptions fetched per job. Since 2026-09-08 two passes: `Vancouver, BC` (20 queries, unchanged) + `Canada` `remote_only` (12×20 — only `is_remote`-flagged or "remote"-in-location rows survive; LinkedIn descriptions deferred to the post-prefilter scraper on this pass). ZipRecruiter and Glassdoor removed 2026-09-28 (Cloudflare 403 / jobspy 400). Whole master query list on both passes since 2026-09-28; Canada pass 35/query. A France `Télétravail` Indeed pass was tried and removed (0 relevant). |
| `adzuna` | free key | ~5 s | ~40–150 | Canada-wide aggregator. Since 2026-09-02 queries match the **title only** (`match: title`): 39 relevant results instead of ~530 mostly-irrelevant ones. Since 2026-09-08 two passes: `where: [Vancouver, Canada]` — country pass sends no distance param; its non-Vancouver on-site rows die in the prefilter pre-scrape. Descriptions are truncated to 500 chars by Adzuna. |
| `workday` | none | ~70 s | ~75 | Big Vancouver employers that post only on their own Workday board (UBC, Aritzia, STEMCELL…). Public `wday/cxs` API; add tenants in `search.yaml` (`tenant`, `wd`, `site` from the careers URL). Full descriptions, one request per new relevant posting (`max_details_per_run`). |
| `eluta` | none | 13 s | ~60 | Canadian aggregator of employer career sites, Vancouver radius. Search results are HTML; the job pages are bot-walled, so scoring uses the search snippet only (low confidence). Catches health authorities, biotech and engineering firms the big boards miss. |
| `himalayas` | none | 30 s | ~450 | Remote jobs with `country=CA` (+`exclude_worldwide`) + worldwide; server-side `sort=recent`, entry/mid seniority, full-time (2026-09-28). EU country passes tried and reverted: `locationRestrictions` is an explicit residency list. Sends a plain User-Agent (browser UAs get 403). Full descriptions. Postings labelled Director/Executive/VP/C-Level are dropped at the source (`skip_seniority`). |
| `ats_companies` | none | ~2 min | 100–600 | ~150 Greenhouse/Lever/Ashby boards from `search.yaml`. Title must contain an ops phrase; location must be Canada/remote-not-elsewhere. Run `autojob companies verify` monthly. |
| `jobicy` | none | 4 s | ~80 | Remote, `geo=canada`, by industry tag. |
| `jooble` | free key (lifetime cap) | 1 s | ~70 | Full 30-query master list per run, split across 2 geos. Swap keys with `scripts/jooble_key.sh`. Snippets only. |
| `themuse` | none | 1 s | ~60 | Filtered to entry/mid levels; includes non-Canadian remote roles the LLM then skips. |
| `weworkremotely` | none | 1 s | ~50 | Category RSS feeds. Mostly senior/US; prefilter handles most. |
| `remoteok` | none | 1 s | ~30 | Single public feed filtered by tag. |
| `jobbank` (Government of Canada) | none | 13 s | ~25 | Location parameter is ignored by the site; province codes are dropped by the prefilter. Low yield. |
| `serper` (Google) | key, 2,500 credits (new key 2026-09-28) | 10 s | ~480 | `queries_per_run` 48 searches rotate through the 9-step `plan` (ATS domains, Wellfound, T-Net, city) — ~96 credits/day at 2 runs/day; spend tracked in the `meta` table (serper.dev has no balance API, `/api/credit` 404s). Every ATS-domain search is scoped `(Vancouver OR Canada)` — unscoped, 98 of 99 results were US/India Workday postings. Free accounts: `num` ≤ 10, no `gl`/`hl`. |
| `amazon` (amazon.jobs public JSON) | none | 2 s | ~170/day | Full descriptions + basic quals inline → zero scrape cost. Vancouver-scoped (added 2026-09-07). |
| `hn` (Who-is-hiring via Algolia) | none | 2 s | ~45/month | Monthly thread; titles are rough but scoring copes. |
| `remotive` | none | 1 s | ~20 | The public API now returns a small recent slice regardless of parameters. |
| `yc` | none | 2–5 min | 5–30 | Discovers "hiring" YC companies via their Algolia index, detects each company's ATS (cached 30 days incl. negatives), pulls ops roles. `max_new_probes_per_run` bounds the cost. |

| **Added 2026-09-28** (research: `RESEARCH-sources-{france,europe,canada}-2026-09-28.md`) | | | | Owner rule: only remote jobs doable from Vancouver; "remote" with no stated residency is kept. Sources with explicit residency lists filter at source. |
| `workable_search` | none | ~75 s | ~25 | `jobs.workable.com/api/v1/jobs` — every Workable employer. Passes: Vancouver (any workplace), Canada remote. Europe/France passes removed after review (junk). |
| `wttj` (Welcome to the Jungle) | public Algolia key | 3 s | ~30 | Full-remote France (the only reliable "full remote" filter), Canada remote, Vancouver. Job pages 403 to scripts → expire by age only. |
| `successfactors` | none | ~65 s | ~60 | RSS feeds: ICBC, BCLC, FortisBC, TELUS, Coast Capital, City of Vancouver, Teck, Scotiabank, Rogers, CN. Full descriptions inline. |
| `getro` | none | ~15 s | ~7 | VC portfolio boards (Real Ventures, Inovia, Georgian; Atomico, Point Nine, HV, MMC, Speedinvest, Earlybird, Daphni). EU boards mostly country-pinned → dropped. No descriptions (scraped later). |
| `remoterocketship` | none | ~20 s | ~40 | Page-embedded JSON; Canada + worldwide title pages (+3 Europe pages). Allowed-countries list must include Canada/NA/worldwide. ToS risk medium — keep the page list short. |
| `workingnomads` | none | 1 s | ~5 | Undocumented `_search` endpoint; allowed-locations list must include Canada/NA/worldwide. |
| `gcjobs` | none (session) | ~50 s | ~25 | Government of Canada jobs, **separate employers only** (CMHC, Bank of Canada, CRA…) — core public service gives citizens preference (PSEA s.39). Bilingual flag in the snippet. Skips title|company dedupe. |
| `bcps` | none | 2 s | ~4 | BC Public Service (hrsmart), Lower Mainland. Skips title|company dedupe. |
| `apec` | none | 9 s | ~6 | **Disabled** — 0 relevant in review; detail pages DataDome-walled; code 20767 = "télétravail total". |

Ideas not implemented: Wellfound direct (no API, blocks scraping — covered via serper plan step instead), WorkBC (JavaScript app), Glassdoor/ZipRecruiter scraping (bot-walled — jobspy attempt live but returns 0), Workable widget API (needs a slug list — `autojob companies probe` could be extended), bcjobs.ca (404 to scripted requests), Working Nomads (developer-heavy), more Workday tenants (lululemon, Teck, BCIT, SFU, TELUS — the tenants exist but their site names were not found; open the careers page, copy the path segment after `myworkdayjobs.com/`). T-Net (bctechnology.com) direct fetch is Cloudflare-walled; covered by a serper `site:` plan step instead.

# Deep Research: Expanding Job Sourcing Volume

**Date:** 2026-09-07 · **For:** shortlist pipeline (`~/projects/shortlist`)
**Question:** How do we scour the internet hard enough to actually use the ~1,000 free OpenRouter calls/day we have for scoring?

---

## 0. The math that frames everything

Current daily run (runs 13–15, Sep 5–6):

| Stage | Volume/day |
|---|---|
| Fetched | ~2,200 |
| New after dedupe | ~190–270 |
| Prefiltered out | ~100–140 |
| **LLM-scored** | **~87–131** |
| OpenRouter free budget | 1,000 calls/day |
| **Unused budget** | **~850–900 calls/day (87%)** |

Docs generation is already on-demand-only (dropped 2026-09-07), so nothing competes with scoring anymore. The LLM budget is not the bottleneck — **discovery of net-new relevant postings is**. To saturate 1,000 scoring calls/day we need roughly **2,000 new jobs/day** surviving dedupe (≈50% prefilter pass rate) — about **7–8× today's volume**. That is achievable because the current 9 active sources structurally miss entire categories (below), not because the internet lacks jobs.

Side note: the 2026-09-07 audit killed 6 sources for low yield (jobbank, remotive, remoteok, jobicy, themuse, yc). Everything below is chosen against the same bar: *does it plausibly yield Vancouver/Canada ops-adjacent postings at ≥1 queued job per week*. Plan to re-audit after 2 weeks of data.

---

## 1. Free, public ATS job-board APIs (the structural gap)

Most companies' careers pages sit on an ATS that exposes a **public JSON endpoint — no key, no browser, no anti-bot**. It's the same data the careers page renders. The pipeline already speaks Greenhouse/Lever/Ashby (`autojob/ats.py`); it does **not** speak six other platforms:

| ATS | Endpoint (GET unless noted) | Notes |
|---|---|---|
| Greenhouse ✅ have | `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | full HTML descriptions |
| Lever ✅ have | `api.lever.co/v0/postings/{slug}?mode=json` | full descriptions |
| Ashby ✅ have | `api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` | salary included |
| **SmartRecruiters** ❌ | `api.smartrecruiters.com/v1/companies/{id}/postings?limit=100` | paginated; used by many Cdn enterprises (Telus uses Workday, but TransLink/others are SR) |
| **Recruitee** ❌ | `{company}.recruitee.com/api/offers/` | descriptions inline |
| **Breezy** ❌ | `{company}.breezy.hr/json` | list has no descriptions (needs per-job fetch) |
| **BambooHR** ❌ | `{company}.bamboohr.com/careers/list` | JSON |
| **Personio** ❌ | `{company}.jobs.personio.com/xml` | XML feed (parse w/ stdlib) |
| **Workable** ❌ | `apply.workable.com/api/v1/widget/accounts/{id}?details=true` + `/jobs` | serper already `site:`-queries these but we never pull the API |
| **Workday** ✅ have | POST `{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | needs tenant+dc+site from careers URL |

Sources: [noble-ronin/ats-job-apis](https://github.com/noble-ronin/ats-job-apis), [dev.to guide](https://dev.to/primeflowio/how-to-pull-every-open-job-from-greenhouse-lever-ashby-and-smartrecruiters-with-public-apis-and-55l5), [Ashby docs](https://developers.ashbyhq.com/docs/public-job-posting-api).

**Why this matters:** a 404 on one vendor just means "not on that ATS" — the existing `autojob companies probe` flow can try them all in sequence. Adding 4–6 fetchers to `ats.py` (~15–25 lines each, same shape as `fetch_lever`) multiplies the hit rate of *every* future company we add, forever. This is the highest-leverage code change in this report.

---

## 2. The company-directory datasets (skip discovery, download it)

Two ready-made, free datasets map **companies → ATS vendor → board slug**, built by enumerating the public APIs above:

1. **LastRound AI ATS Directory — 9,935 companies, CC BY 4.0**
   [datahub.io/lastroundai-hiring-data/ats-directory](https://datahub.io/lastroundai-hiring-data/lastroundai-hiring-data/ats-directory) (DOI 10.6084/m9.figshare.33154145)
   Columns: `ats_vendor` (greenhouse 4,966 / ashby 2,856 / lever 2,113), `company_name`, `board_slug`, `last_crawled` (Jul–Aug 2026). No location column — filter by probing the board and reading job locations.
2. **groundtruthtools/ats-jobs-mcp — 7,479 boards mapped** ([GitHub](https://github.com/groundtruthtools/ats-jobs-mcp)) — overlapping, different crawl.
3. **ever-jobs slug directory** ([COMPANY_SLUG_DIRECTORY.md](https://github.com/ever-jobs/ever-jobs/blob/6eedb2ed/docs/COMPANY_SLUG_DIRECTORY.md)) — curated + verified, smaller.

**Play:** one-off script — load dataset → skip slugs already in `ats_companies` config → probe each candidate → keep boards whose postings include Vancouver/BC/`Remote (Canada)`. The `company_ats_cache` table (30-day cache) already supports this pattern. Realistic yield: a few hundred Canada-relevant boards vs the ~100 currently configured (mostly US tech). Even a 20% hit rate on ops-relevant titles is more scored jobs than today's total.

**Caveat:** CC BY 4.0 requires attribution — a comment in `search.yaml` linking the dataset covers it (repo is public).

---

## 3. Workday tenant expansion (3 → 30+)

Workday is where **big BC employers live and nowhere else** (already proven: UBC, Aritzia, STEMCELL). Only 3 tenants are configured. Discovery is the bottleneck; three feeds solve it:

- **TheirStack: 1,307 Canadian companies on Workday** ([theirstack.com/en/technology/workday/ca](https://theirstack.com/en/technology/workday/ca)) — scraped list, verify each careers URL.
- **BC's Top 100 Employers (2026)** ([canadastop100.com/bc](https://www.canadastop100.com/bc/)) + **Canada's Top 100 Employers** ([canadastop100.com/national](https://www.canadastop100.com/national/)) — static winner pages, ~100–150 orgs each, heavy on BC health authorities, universities, crown corps, big retailers — exactly the employers that post ops/coordinator/analyst roles and never list on LinkedIn-first aggregators. Annual refresh (Feb).
- **Serper `site:myworkdayjobs.com` queries** — already in the plan rotation; keep as the discovery net that feeds `autojob companies probe`.

Each tenant adds 20-posting pages × `pages_per_query`. Health authorities (Vancouver Coastal, Fraser, Providence), TransLink, BC Hydro, ICBC, lululemon, Best Buy Canada, London Drugs, Vancity, Coast Capital — most are Workday or SmartRecruiters. Target: **25–35 tenants**.

---

## 4. jobspy: two boards you already own but don't use

`boards.sites: [linkedin, indeed]` — but jobspy also supports:

| Site | Verdict | Evidence |
|---|---|---|
| **zip_recruiter** | **Add now.** US/Canada only, uses `location` param, moderate rate limiting, full descriptions via API | [jobspy ziprecruiter docs](https://mintlify.wiki/speedyapply/JobSpy/job-boards/ziprecruiter) |
| **glassdoor** | Experiment. Known failure class: CSRF URL 404 after Next.js migration → silently returns 0 jobs | [PR #347](https://github.com/speedyapply/JobSpy/pull/347), [issue](https://github.com/joeyspagnoli/agentic-job-applier/issues/9) |
| **google** (Google Jobs) | Skip. "Initial cursor not found" / needs clean residential IP; home-lab IP almost certainly blocked | [issue #302](https://github.com/speedyapply/JobSpy/issues/302) |

`zip_recruiter` is a **one-line config change** (`sites: [linkedin, indeed, zip_recruiter]`) — different aggregator index, so new-dedupe rate should be high. Glassdoor: add behind the same "0 jobs for N days → disable" measurement that killed the dead six. Google Jobs: don't bother, Serper already covers that index.

---

## 5. Vancouver/BC-specific boards (structurally missing today)

These index **employer career sites the big aggregators miss** — same reason Eluta survived the audit:

1. **T-Net / bctechnology.com — RSS job feeds, no key**
   BC's #1 tech job board (~1,075 listings). RSS feeds per category: [bctechnology.com/jobs/rss-feeds.cfm](https://bctechnology.com/jobs/rss-feeds.cfm). Implementation = copy of `weworkremotely.py` (feedparser). Covers BC tech employers (Arista, etc.) with direct links.
2. **BCtechjobs.ca — public REST API v1.1, no key**
   [bctechjobs.ca/developer/jobs](https://www.bctechjobs.ca/developer/jobs) — `api/v1.1/jobs/{id}`, employer/category/location objects, autoRefresh status. Straightforward JSON source (~60 lines).
3. **amazon.jobs — public JSON search, no key**
   `https://www.amazon.jobs/en/search.json?result_limit=100&city=Vancouver&country=CAN&sort=recent` (params: `base_query`, `category[]`, `schedule_type_id[]=Full-Time`, `loc_query`, `radius`) — **full descriptions + qualifications inline**, so zero scrape cost. Amazon Vancouver posts real ops/program roles. Sources: [SO](https://stackoverflow.com/questions/49495370/), [jobseek monitor impl](https://github.com/colophon-group/jobseek/blob/143aa449/apps/crawler/src/core/monitors/amazon.py).
4. **Careerjet Canada — affiliate API, free key, medium friction**
   [careerjet.ca/partners/api](https://www.careerjet.ca/partners/api) — `search.api.careerjet.net/v4/query` with basic-auth key. Friction: registration tied to a domain + **mandatory IP whitelist** ([field report](https://dev.to/rsvlim/gemini-called-it-a-public-api-careerjets-registration-portal-disagreed-2aaf)). Worth it only if T-Net + bctechjobs underdeliver; the home IP is static, so whitelisting is feasible.
5. **HN "Who is hiring" — free, no key, monthly**
   `hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring` → latest thread → fetch comments → regex `Vancouver|Canada|Remote`. Ops roles are a minority but it's ~5 requests/month and catches startup roles nobody cross-posts. ([HN API](https://hn.algolia.com/api), [example impl](https://github.com/melons/melons-agents/blob/main/skills/job-hunt/sources/global-hn-whoshiring.sh))

---

## 6. Discovery engines (keep the funnel full for months)

These don't list jobs — they find **companies to add** to `workday.tenants` / `ats_companies`:

1. **Serper `/news` endpoint** — same key/account as `/search`: `POST google.serper.dev/news {"q": "Vancouver company expanding hiring 2026", "gl": "ca"}`. Hiring press releases ("opening Vancouver office, creating 300 jobs") are the earliest signal that exists — before postings hit any board. Output = company names → `autojob companies probe`. Cost: a few credits/day. ([Serper News API spec](https://apis.io/apis/serper/serper-news-api/))
2. **Common Crawl CDX index — enumerate ATS boards at web scale, free**
   [index.commoncrawl.org](https://index.commoncrawl.org/) supports wildcard URL queries against the monthly crawl: `jobs.lever.co/*`, `boards.greenhouse.io/*`, filtered by `filter=url:...`. This is the "reverse discovery" pattern (start from the ATS, not from a company list — see [career-ops #745](https://github.com/santifer/career-ops/issues/745)). Overkill **unless** Tier 1–5 don't saturate the LLM budget; then it's the only method that scales past curated lists. Monthly refresh cadence matches crawl cadence.
3. **The annual employer lists** (§3) as a yearly cron: scrape winner pages each February → probe pipeline.

---

## 7. Budget & capacity notes for 1,000 scoring calls/day

- **RPM:** free OpenRouter models are capped ~20 RPM each; 1,000 calls at one model = ~50 min. With the 4-model fallback chain interleaving, a 45–60 min run absorbs it. If runs stretch, split into two runs (below).
- **`max_llm_calls_per_run: 800`** → raise to 1,000 (or `950` leaving docs headroom — docs are on-demand though, and count against the same daily 1,000).
- **`max_scrapes_per_run: 300`** will bottleneck first. Greenhouse/Lever/Ashby/Recruitee/amazon.jobs return descriptions **inline in the list response** — no scrape needed. Prefer sources with inline descriptions as volume grows. Otherwise raise to ~600–800 (each ~1.5 s ⇒ +8–12 min run time).
- **Two runs/day (07:00 + 19:00):** job postings close fast; a second sweep catches same-day postings and halves the window a fresh posting can be missed. Free — same keys, same credits, and it flattens the RPM constraint (2 × 500 calls). Recommend regardless of sourcing changes.
- **Dedupe load:** ~2,000 new rows/day on `jobs` + fingerprint index is nothing for SQLite; `seen_urls` grows ~60k/month — fine for months, add an index-agnostic cleanup only if runs slow.
- **Prefilter stays as-is.** Volume should come from more sources, not looser filters — precision is what keeps 1,000 calls/day affordable. The one candidate relaxation: direct-ATS sources have exact `posted_at`, so `max_posted_age_days: 30` could safely become 45 for those (catches evergreen postings on employer boards that aggregators rotate out).

---

## 8. Build order (impact ÷ effort)

| # | Change | Effort | Expected new jobs/day |
|---|---|---|---|
| 1 | `boards.sites += zip_recruiter` | 1 line | +100–300 fetched |
| 2 | Second daily run (07:00 + 19:00) | timer edit | freshness ↑, same volume |
| 3 | T-Net RSS source | ~50 lines (clone WWR) | +50–150 |
| 4 | amazon.jobs source (CAN+Vancouver) | ~60 lines, no scrapes needed | +30–80, full descriptions |
| 5 | bctechjobs.ca API source | ~60 lines | +20–60 |
| 6 | ATS fetchers: smartrecruiters, recruitee, workable, breezy, bamboohr, personio | ~20 lines each in `ats.py` | multiplies #7/#8 yield |
| 7 | LastRound 9,935-company dataset → probe → `ats_companies` (CA-filtered) | one-off script | +100–400 |
| 8 | Workday tenants 3 → 30 (TheirStack + Top Employers lists) | config + verify | +100–300 |
| 9 | Serper `/news` hiring-announcement discovery | ~40 lines + credits | compounding (new companies) |
| 10 | Glassdoor via jobspy (behind auto-disable guard) | 1 line + audit | 0–100, uncertain |
| 11 | HN Who-is-hiring | ~40 lines, monthly | +5–20 |
| 12 | Common Crawl CDX enumeration | 1–2 days | unbounded; only if needed |
| — | Careerjet CA (IP whitelist) | reg + ~60 lines | only if #3/#5 underdeliver |

Steps 1–8 are the realistic path to **~700–1,000 scored jobs/day** (roughly the full free LLM budget). Steps 9+ keep discovery compounding after the curated lists saturate.

---

## 9. Explicitly rejected / deprioritized

- **jobspy Google Jobs** — residential-IP requirement, cursor bugs (issue #302). Serper already buys us the Google index.
- **Wellfound direct scraping** — Cloudflare-walled; the existing `site:wellfound.com/jobs` Serper step is the right cost.
- **YC / Work at a Startup** — dead, already disabled.
- **The 6 dead sources (Sep 7 audit)** — leave off unless an expansion changes their math (they won't).
- **Relaxing the prefilter to inflate scored volume** — burns LLM calls on noise; defeats the point of spending the budget on *scoring*.
- **Careerjet now** — IP-whitelist + domain registration friction for uncertain marginal gain over #3/#5.

---

## 10. Sources consulted

jobspy docs/issues ([troubleshooting](https://mintlify.wiki/speedyapply/JobSpy/troubleshooting), [ziprecruiter](https://mintlify.wiki/speedyapply/JobSpy/job-boards/ziprecruiter), [#302](https://github.com/speedyapply/JobSpy/issues/302), [#347](https://github.com/speedyapply/JobSpy/pull/347)) · [noble-ronin/ats-job-apis](https://github.com/noble-ronin/ats-job-apis) · [primeflow dev.to ATS guide](https://dev.to/primeflowio/how-to-pull-every-open-job-from-greenhouse-lever-ashby-and-smartrecruiters-with-public-apis-and-55l5) · [LastRound AI ATS Directory](https://datahub.io/lastroundai-hiring-data/lastroundai-hiring-data/ats-directory) · [groundtruthtools/ats-jobs-mcp](https://github.com/groundtruthtools/ats-jobs-mcp) · [Ashby Posting API](https://developers.ashbyhq.com/docs/public-job-posting-api) · [TheirStack Workday Canada](https://theirstack.com/en/technology/workday/ca) · [resumeadapter verified Workday list](https://www.resumeadapter.com/ats/workday/companies) · [canadastop100.com/bc](https://www.canadastop100.com/bc/) · [T-Net RSS](https://bctechnology.com/jobs/rss-feeds.cfm) · [BCtechjobs API](https://www.bctechjobs.ca/developer/jobs) · [amazon.jobs search.json](https://stackoverflow.com/questions/49495370/) · [jobseek amazon monitor](https://github.com/colophon-group/jobseek/blob/143aa449/apps/crawler/src/core/monitors/amazon.py) · [Careerjet API](https://www.careerjet.ca/partners/api) + [friction report](https://dev.to/rsvlim/gemini-called-it-a-public-api-careerjets-registration-portal-disagreed-2aaf) · [HN Algolia API](https://hn.algolia.com/api) · [HN whoshiring impl](https://github.com/melons/melons-agents/blob/main/skills/job-hunt/sources/global-hn-whoshiring.sh) · [Common Crawl Index Server](https://index.commoncrawl.org/) · [career-ops reverse-discovery](https://github.com/santifer/career-ops/issues/745) · [Serper News API](https://apis.io/apis/serper/serper-news-api/)

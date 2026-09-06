# Audit: Sourcing Expansion (report §8 build order) — 2026-09-07

Implementation of `docs/RESEARCH-sourcing-expansion-2026-09-07.md`, then audited same day.
**Re-audit date: 2026-09-21** (2 weeks of `source_runs` data) — SQL at the bottom.

## Audit table

| # | Change | Status | Evidence / notes |
|---|---|---|---|
| 1 | `boards.sites += zip_recruiter` | ⚠️ live but 0 jobs today | jobspy returns silently-0 from this IP for zip in every query/geo combo tested; linkedin+indeed unaffected in combined runs (25+25). Watch 2 weeks → disable if still 0. |
| 2 | Second daily run 07:00 + 19:00 | ✅ | `autojob.timer` has both OnCalendar slots; first 19:00 run tonight. Flattens the 20-RPM OpenRouter cap and halves the fresh-posting miss window. |
| 3 | T-Net RSS source | ❌ blocked — not built | Whole bctechnology.com domain (incl. feed endpoints) Cloudflare-challenges this server's IP. Fallback when wanted: serper plan step `site:bctechnology.com` (1 credit/query, zero code). |
| 4 | amazon.jobs source | ✅ **169 jobs live** | `sources/amazon.py`, full descriptions + basic quals inline → zero scrape cost. Dry-run scored it end-to-end (dev roles correctly SKIPped, 0 errors). |
| 5 | bctechjobs.ca source | ❌ blocked — not built | API now requires an API-Key header (401 Anonymous). Same friction class as Careerjet; revisit only if other BC sources underdeliver. |
| 6 | ATS fetchers | ✅ 4 of 6 | Added smartrecruiters, recruitee, workable, personio to `ats.py` (+ probe + companies verify). Live-verified: smartrecruiters (AveryDennison board), workable envelope (companies news probe). **Breezy + BambooHR skipped** — their documented endpoints returned HTML/empty from here; blind code. |
| 7 | LastRound dataset probe | ✅ 24 boards kept / 400 probed | `scripts/expand_ats_boards.py` (CC BY 4.0 attribution in search.yaml + script). 5.9% hit rate; resumes automatically (30-day probe cache), ~9.5k candidates left. Rerun weekly-ish. |
| 8 | Workday tenants 3 → 21 | ✅ 18 added | Serper discovery (51 credits) + two-stage verification (API smoke test, then 20-posting location check; caught serper returning wrong companies' boards — e.g. "Fraser Health"→Ascension). Dropped: McGill (locations are building names — breaks prefilter), Walmart/Four Seasons (US boards), SFU/VCH/TransLink/ICBC/lululemon/etc (not on public myworkdayjobs.com). |
| 9 | Serper /news discovery | ✅ works | `autojob companies news` — 3 credits/run, extracts company names from hiring PR, probes all 7 ATS vendors. Live test found a Workable board. Run weekly-ish, curate hits into search.yaml. |
| 10 | Glassdoor via jobspy | ⚠️ added, 0 jobs | Same silent-0 class as zip. Same watch-then-kill treatment. |
| 11 | HN Who-is-hiring | ✅ 46 jobs live | `sources/hn.py` via Algolia (2 requests/month). Titles are rough (picks shortest matching pipe-segment) — scoring copes; it's a ~45-job monthly long tail. |
| 12 | Common Crawl CDX | ⏭️ skipped | Per report: only if 1–8 don't saturate the budget. |
| — | Careerjet | ⏭️ skipped | IP-whitelist + domain registration friction (report §9). |
| — | Caps | ✅ | `max_llm_calls_per_run` 800→1000, `max_scrapes_per_run` 300→600 (report §7). |

## Verified totals (live, 2026-09-07)

- New jobs/day capacity added: amazon 169 + HN ~45/mo + 24 discovered boards + 18 workday tenants (UBC alone posts 117; banks 500–2000 each, pre-filtered per job)
- Dry-run `--sources amazon,hn,ats_companies`: 490 fetched, 206 new, 17 scored, **0 errors**
- Serper spend today: 117/2500 (51 workday discovery + 3 news + 63 prior)
- Timer: 07:00 + 19:00 both active

## Re-audit SQL (run 2026-09-21)

```sql
SELECT source, COUNT(*) n, SUM(status='queued') queued, ROUND(AVG(score),1) avg_score
FROM jobs WHERE first_seen >= date('now','-14 days') GROUP BY source ORDER BY queued DESC;
```
Kill anything with ≥50 fetched and 0 queued (the bar that killed the Sep-7 six). Check zip_recruiter/glassdoor specifically (jobspy site breakdown lives in logs: `grep '\[boards\]' data/autojob.log`).

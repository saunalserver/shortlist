# Changelog

## 2.1.2 — 2026-09-02 (resume tailoring rewritten)

- The model no longer edits resume LaTeX. On the first live test with the new CV it had added "Microsoft Office" and "AI tool integration", dropped the $100K/month figure and rewritten bullets into different claims — despite a prompt forbidding all of it. Now the template is parsed into summary + bullets per section; the model returns a bullet order (and at most one drop per section) plus a summary that is rejected if it cites a number or tool absent from the template. Overflow is handled by dropping trailing bullets, no second model call.
- New resume template installed (Sept 2026 CV with the Peakflow role, `microtype`); scoring profile updated with the Peakflow role, growth/attribution skills and two side projects.

## 2.1.1 — 2026-09-02 (keywords + profile)

- Search queries reordered into a 26-item volume-to-fit list; the first 10 are what LinkedIn/Indeed see (cap raised 10 → 20), the first 8 Job Bank, the first 6 Jooble/Eluta. Serper gets its own 8-item list so its 12-credit rotation cycles in ~5 days. Dropped "workflow automation" (a skill) and "automation specialist" (PLC/controls in BC).
- Career-page title filters (Greenhouse/Lever/Ashby, YC, Workday) now also catch solutions, technical account, customer success, data/systems analyst, partnerships, process, GTM, reporting, revenue titles.
- Title exclusions: plc, controls, site, trades, civil, nursing, building/industrial automation, process engineer; whole-word matching now accepts plurals ("Drivers", "Nurses"). Checked against this month's shortlist: nothing scored ≥ 6 is affected; 260 of the 665 postings that scored ≤ 3 would now be dropped before the LLM.
- Profile: 27 target roles; ranking preferences (bilingual EN/FR, US-facing remote from Canada is fine, small-to-mid companies). Scorer gets matching +1 signals and a −1 for very large enterprises.
- Tracker reset to empty; pipeline apply/dismiss decisions cleared.

## 2.1.0 — 2026-09-02 (stress test after the first two full runs)

**Fixed**
- **Budget cap marked jobs as errors.** When the 400-call LLM budget was hit, `LLMBudgetExceeded` was swallowed by the scorer, so every remaining job was written as `error` one by one (171 on run 4) and the digest reported "171 errors". The exception now propagates; leftovers stay `new`.
- **Digest missed carry-over jobs.** It selected by `run_id`, so jobs fetched earlier and scored today were left out (3 of 8 on run 4). Now selects by scoring time.
- **"Chief of Staff" was never scored.** `chief` and `staff` are title exclusion words; 12 such postings were dropped. New `title_allow_phrases` protects target titles.
- **Model broke the resume preamble** (`setspace` → `setspacing`, pdflatex failed, untailored fallback shipped). The template's preamble is now always spliced back in.
- **503 storms cost 25 minutes per run.** 148 retries × 5–15 s sleeps on `gemini-3.5-flash-lite`. Overloaded models now go on a 90 s cooldown after one quick retry and the next model takes the call.
- **Duplicate detection missed company spelling variants** ("The University of British Columbia" vs "University of British Columbia", "Agentis Capital" vs "Agentis Capital Advisors"). Fingerprints now use a two-word company key; all rows recomputed (schema v3).
- Worker service had been running pre-rebuild code since 2026-09-01 (never restarted after the subprocess change); restarted.

**Added**
- **Expiry.** New status `expired`, `autojob expire`, and an expiry step at the start of every run: shortlisted jobs older than `expiry.posted_max_days` (30) — or `fetched_max_days` (45) when the source gave no date — are retired, and up to `link_checks_per_run` posting pages are fetched to catch 404 / "no longer accepting applications". 430 stale May–July postings retired on first run.
- **Posting-age prefilter** (`max_posted_age_days`): 107 postings scored on 2026-09-02 were already older than 30 days when fetched.
- **Location rules rewritten:** a named non-local Canadian city on an on-site posting is dropped even when the string also says "Canada"; US-only markers, states and 51 US cities now apply to remote postings too; 64 foreign countries/regions drop "Remote - EMEA"-style postings. Multi-city postings naming the Vancouver area are kept.
- ~90 more title exclusion words/phrases and part-time/temporary/seasonal/casual employment types, from a review of everything that scored 1–2.
- Sources: **Workday** (UBC, Aritzia, STEMCELL — add more tenants in `search.yaml`) and **Eluta.ca** (snippet-only).
- Adzuna matches query words in the title only (39 relevant results instead of ~530). Serper ATS-domain searches scoped to `(Vancouver OR Canada)`, titles cleaned of `- Myworkdayjobs.com`-style suffixes, Workday locations parsed from URLs. Himalayas drops Director+ postings at the source. LinkedIn/Indeed 25 results per query (was 15).
- Scraper refuses bot-wall pages ("are you a human?") instead of storing them as descriptions.
- Dashboard: `expired` status, Posted column with age, sort by newest posting / most recently scored, "Shortlisted last 7 days" and "Retired" cards, retired count per run.

## 2.0.0 — 2026-09-01 (rebuild)

The April–June 2026 version (tag `legacy-2026-09-01`) was a flat set of `fetcher_*.py` scripts. This release is a package.

**Fixed**
- Jobs were deleted and un-remembered at the start of every run, so the same ~550 postings were re-fetched and re-scored daily (≈3 h and 550 LLM calls per run). Jobs are now kept forever; dedup by canonical URL + title|company fingerprint.
- Serper had been failing on every query since June (credits exhausted; later the free-tier `num`/`gl`/`hl` rules). Now budgeted (`queries_per_run`) with a rotating plan and correct parameters.
- YC source probed ~1,600 companies for ~25 min per run for 8 jobs; negative lookups were never cached. Now cached 30 days and capped per run (85 s).
- The cover letter "template" was a finished letter for one company and the model rewrote the whole LaTeX file (frequent 2-page/pdflatex failures). Now the model returns JSON rendered into a fixed template, first person, one-page retry.
- Telegram sent one message per generated job (rate-limited daily). Now one digest per run.
- Himalayas 403 (User-Agent), Job Bank selectors, `is_canada_or_remote("Québec")` matching `bc`, dead Lever/Greenhouse slugs (33 pruned).

**Added**
- Sources: Jobicy, The Muse, We Work Remotely, Lever and Ashby company boards (the old `fetcher_lever.py` was actually LinkedIn/Indeed and the Lever list was never used).
- Rule prefilter before the LLM; per-model rate limits and fallback list; per-run budgets for scrapes and LLM calls.
- `runs` / `source_runs` tables and a dashboard Sources page (per-source yield, errors, duration).
- `commands` queue + `autojob worker` so the dashboard can start runs and generate documents without Python in the container.
- CLI: `run`, `docs`, `sources list|test`, `companies verify|probe`, `stats`, `action`, `worker`, `doctor`. Tests (`pytest`), lint (`ruff`), `scripts/install.sh`, systemd user units.
- Personal data moved out of code: `profile/` (git-ignored) and `profile.example/`.

**Removed**
- FastAPI mini-dashboard (`web/`), `tracker.py` cross-writes into the tracker DB, `pipeline_jobs` archive, WorkBC stub, threaded pause/resume, 100+ unused config constants, `autojob-v2/` and `autojob-shareable/` directories (kept as branches).

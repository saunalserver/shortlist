# Database Health Review — `autojob.db` + `jobsearch.db` (Slice 2, 2026-10-06)

All queries ran against read-only URIs (`?mode=ro`). No files were created, modified, or deleted. Server clock at review time: 2026-10-06 18:01 UTC (11:01 PDT). Git HEAD confirmed `877686c` (v2.4.0, 2026-09-29).

---

## 1. Schema, row counts, sizes

### `pipeline/data/autojob.db` — 114,020,352 bytes on disk (109 MiB) + 8.76 MB WAL

| table | rows | size (dbstat) | notes |
|---|---|---|---|
| jobs | 26,398 | 96.4 MB (88% of DB) | 34 columns incl. `description` (66.2 MB of text total, avg 2,631 chars/row) |
| seen_urls | 36,345 | 3.3 MB + 2.65 MB pk index | URL-level dedupe, oldest 2026-09-03 |
| company_ats_cache | 10,195 | 0.66 MB | probe_count max 2, last_probed max 2026-09-07 |
| ats_boards | 823 | 0.11 MB | **all 823 are `ashby`** — actively used by the `boards`/serper site: queries |
| source_runs | 888 | 0.05 MB | seq=952 → 64 rows deleted |
| runs | 71 | 0.01 MB | seq=80 → ids 1–9 deleted |
| meta | 1 | — | `serper_credits_used = 817` |
| pipeline_state | 1 | — | idle/done, healthy |
| commands | 1 | — | seq=3 → ids 1–2 deleted; feature nearly unused |

- `PRAGMA integrity_check` = **ok**; journal_mode = **wal**; freelist = **1 page** (no bloat); auto_vacuum = none; page_count 27,844 × 4,096.
- **~22,264 job rows were deleted historically**: ids run 22,265–48,662 contiguous (0 gaps), min `fetched_at` = 2026-09-03T00:44:56. This is the 2026-09-02/03 reset (matches `autojob.db.bak-2026-09-02`, 17 MB). `seen_urls` was kept through the reset — that's why 9,947 seen URLs have no job row (correct, dedupe-by-design).

### `dashboard/data/jobsearch.db` — 32,768 bytes + 317 KB WAL

| table | rows | notes |
|---|---|---|
| applications | 18 | all `status='applied'`, all `source='other'` |
| companies | **0** | table exists, nothing writes it |

- integrity_check **ok**, wal mode, freelist 0. Two useful indexes (`idx_applications_status`, `idx_applications_date`). Healthy; the only oddity is the dead `companies` table.

### Index usage (EXPLAIN QUERY PLAN on live patterns)
- `status=?` → uses `idx_jobs_status` ✓; `fetched_at` range → `idx_jobs_fetched` ✓; pk lookups ✓.
- **`user_action='dismissed'` → full table SCAN** (no index) — this is the dashboard's main filter.
- `ORDER BY posted_at` → full scan + temp b-tree (no `posted_at` index). Same for `run_id=?` queries. At 26k rows all of this is milliseconds — cosmetic today, worth one partial index only.

---

## 2. Duplicates

- **Fingerprint**: 24,514/26,398 rows have a fingerprint; **0 duplicate fingerprint groups**. (1,884 rows have NULL fingerprint — all from the earliest days, pre-fingerprint.) The dedupe layer works.
- **Exact URL**: unique constraint, 0 dupes. **URL variants** (same URL ignoring query string): **30 groups** — tracking-param variants inserted as distinct rows.
- **Same title+company, different URLs** (surviving rows): **116 groups, 246 rows**, of which 238 were LLM-scored and **109 groups had 2+ rows scored → 123 redundant LLM scoring calls** (~1.3% of the 9,229 lifetime scorings). Worst offenders:
  - Indigo Books & Music "Customer Experience Leader" ×5 (all skipped)
  - JYSK Canada Operations Manager ×5, **JYSK Sales Colleague ×5 (statuses skipped *and* queued — a genuine duplicate queue entry)**
  - Arista Networks TAM ×3, Turner & Townsend PM ×3, Jerry.ai ×3
  - Pattern: SmartRecruiters/Indeed reposts with new job IDs — fingerprint is URL/content-derived and doesn't collide across reposts.
- **seen_urls ↔ jobs**: all 26,398 job URLs exist in seen_urls ✓; 9,947 seen-only (purged era, by design). No orphans in the bad direction.

## 3. Stuck / zombie rows

- **status='new' never processed: 0** (statuses are only prefiltered/skipped/queued/expired/docs_generated). `processed_at` NULL: **0**. Clean.
- **Zombie runs — confirmed and one NEW find**: run **#22** ('running', started 2026-09-09T00:31:33, all counters 0, no finished_at) **and run #53** ('running', started 2026-09-24T13:30:32, same shape). Both are crashed/timeout'd runs never marked dead. All other 69 runs have terminal status (incl. 6 legit 'aborted'/'error' with notes).
- **Commands stuck: 0** — the single row (id 3) is `done`. Table is otherwise unused.
- **Queue reality check (829 'queued')**:
  - **593 are already acted on** (579 dismissed + 14 applied) but keep `status='queued'` forever — the status never flips on user action, so "829 queued" overstates the live queue ~3.5×.
  - **236 unacted**: 230 at score 7, 6 at score ≥8. **176 of 236 are older than 14 days**; 101 rows total are >30 days old (fetched 2026-09-03..05); **0 older than 60 days** (DB is only 34 days old, so nothing is deeply dead).
  - Queue score floor holds: zero queued rows below 6; the 316 score-6 rows are all pre-recalibration and all already acted on.
- **NULL anomalies**: `queued_scored_null=0`, `docs_status=16 = docs_generated_at=16` ✓, `fit_score` NULL only for prefiltered (17,169, by design), `run_id` NULL: 0, `ua_status_mismatch=0` (all user_action rows are queued/docs_generated).
- Minor: 8 of 121 `expired` rows have no `link_checked_at` (expired via posted-date age, not link check). `pipeline_state.pid` (3048596) is stale after run end — cosmetic.

## 4. Dead sources

Lifetime from `source_runs` (fetched = listings pulled, new_jobs = inserted after dedupe):

| source | fetched | new_jobs | yield | avg s/run | status |
|---|---|---|---|---|---|
| boards | 66,726 | 12,091 | 18.1% | **1,500** | active, biggest source (25 min/run!) |
| ats_companies | 60,977 | 1,374 | **2.3%** | 502 | active — worst yield per fetch |
| workday | 52,332 | 1,292 | **2.5%** | 509 | active — 96% re-fetch churn |
| adzuna | 51,719 | 3,816 | 7.4% | 25 | active |
| himalayas | 46,616 | 1,657 | 3.6% | 43 | active |
| serper | 7,767 | 4,123 | **53.1%** | 50 | best yield |
| amazon / jooble / eluta / hn / weworkremotely | 18k/18k/6k/3k/2.2k | 381/875/178/91/93 | 2–5% | 1–12 | active |
| jobicy, themuse, jobbank, remoteok, yc, remotive | 1,283 total | 270 | ~21% | 0–77 | **dead: last run 2026-09-06, disabled since** |
| successfactors, remoterocketship, wttj, gcjobs, workable_search, getro, workingnomads, bcps | 3,089 | 157 | ~5% | 0–69 | new since 09-28 |

- Recent-week productivity (jobs table, W38→W40): boards 2,451→2,594→662(partial), serper 643→1,256→252. New sources contributed 224 rows in W39 (~4% of volume) but 8 queued — proportionally fine.
- **Zero errors ever recorded in source_runs.error** — the column is never populated; failures are invisible here (runs.notes carries them instead).
- `company_ats_cache`: 10,195 companies probed but **nothing probed since 2026-09-07** — the probe pipeline is dormant; cache is read-only ballast now. `ats_boards` (823 ashby) is genuinely consumed by the serper site:-queries.

## 5. Broken dates

- **`posted_at`**: 6,930 NULL (26%); 19,468 stored as bare `YYYY-MM-DD` (no tz — fine as a date convention); **136 rows store unparseable human formats**: weworkremotely → RFC-2822 (`"Wed, 26 Aug 2026"`, 93 rows), jobbank → `"August 13, 2026"` (43 rows). These compare as *future* textually (that's the "136 future" count — **no real future dates** among well-formed ones, max = 2026-10-06). No epoch-zero, none pre-2000. Oldest legit posting: 2020-05-11.
- **Timezone consistency**: every pipeline-written instant (`fetched_at`, `processed_at`, `scored_at`, `docs_generated_at`, `link_checked_at`, runs) is ISO `+00:00` UTC ✓. Two writers use a different textual convention: `jobs.user_action_at` and `commands.created_at` are ISO-Z **with milliseconds** (`2026-09-12T03:51:07.873Z`) — written by the dashboard/API side. Both are unambiguous UTC, so sorting/joins hold; purely cosmetic inconsistency.
- **Bulk-dismissal classification** (distinct timestamps vs rows):
  - **2026-09-12: 352 dismissed / only 52 distinct timestamps** (≈6.8 rows per instant, spread 00:06–20:08) — the only true *bulk* dismissal (recalibration day).
  - **2026-09-28: 45/45 over 66 min**, **2026-10-03: 11/11 over 8 min**, **2026-10-05: 71/71 over 2.4 h** (with 8 applies interleaved) — all **manual rapid triage sessions**, not bulk ops. Likewise 09-05 (48 over 63 min).

## 6. Consistency

- **`output_folder` vs disk — broken in both directions**:
  - **10 rows point to `/home/saunalserver/projects/Autojob-search/output/...` — that path no longer exists** (pre-move repo location). The files actually live under `pipeline/output/` (10 folders in `2026-09-03`, 6 in `2026-09-04` — all 16 match DB rows by name ✓).
  - **44 orphan folders under `pipeline/output/2026-09-02/`** with no DB rows (jobs purged in the 09-02 reset). Total disk: 166 files, 11 MB.
- **`meta.serper_credits_used` = 817**: incremented by exactly two non-overlapping paths — per-run (`pipeline/autojob/sources/serper.py:138-139`) and the manual discover command (`pipeline/autojob/cli.py:155-156`). No double-count; no independent ledger exists to audit against (Serper has no balance API — noted in code).
- **`runs.llm_calls`**: sum = 8,872 vs 9,229 rows with `scored_at` (~4% undercount: free-era runs recorded 0, plus abort-discarded results). Directionally fine.
- **`score_facts` — populated for ZERO rows.** The column was added by migration (`pipeline/autojob/db.py:240-241`) and the write path exists (`pipeline/autojob/pipeline.py:262`, gated on `res.get("facts")`), but `compute_v2` only runs when `scoring.version == 2` (`pipeline/autojob/scorer.py:69`) and **`search.yaml:64` says `version: 1`**. The whole v2 facts→deterministic-score chain shipped in v2.4.0 is dormant — nothing records which facts drove a score.
- **Tracker cross-check (perfect)**: 18 `user_action='applied'` in pipeline ↔ 18 rows in tracker; URL join exact both directions; company names match case-insensitively for all 18; applied dates line up day-for-day. `applications.source` is always `'other'` (not wired to pipeline source); `companies` table unused.

---

## 7. Improvement ideas (ranked: impact ÷ effort)

1. **Mark the two zombie runs dead** (30 seconds, prevents misreads of run history): 
   `UPDATE runs SET status='error', finished_at=started_at, notes='stale running row, process gone — cleanup 2026-10-06' WHERE id IN (22,53) AND status='running';`
   Plus a one-line guard at worker startup: any `runs.status='running'` older than ~6 h with no live pid → mark error. Root cause is crash-without-finally in the run wrapper, not these two rows.
2. **Retention: NULL out descriptions of dead rows** (biggest size win, trivial): prefiltered+skipped rows hold **63.5 MB of description text = 58% of the whole DB file** that nothing will ever read. 
   `UPDATE jobs SET description=NULL WHERE status IN ('prefiltered','skipped') AND fetched_at < datetime('now','-30 days');` then one-time `VACUUM;` (file should drop to ~45 MB). Keep the rows + `prefilter_reason`; `seen_urls` already prevents re-fetch.
3. **Flip `scoring.version: 1 → 2`** (`pipeline/config/search.yaml:64`, one line): lights up `score_facts` + deterministic `compute_v2` weights that v2.4.0 was built for — prerequisite for any future recalibration with data instead of vibes. Validate on ~20 jobs first since every historical row has v1 reasoning.
4. **Cross-source repost dedupe** (medium effort, ~1.3% LLM spend + duplicate queue entries): before scoring, check `SELECT 1 FROM jobs WHERE lower(trim(company))=? AND lower(trim(title))=? AND scored_at > now-14d` and inherit the verdict. Kills the JYSK-style skipped+queued double queue entries and the 123 redundant calls.
5. **Rewrite stale `output_folder` paths + delete 09-02 orphans**: 
   `UPDATE jobs SET output_folder=REPLACE(output_folder,'/home/saunalserver/projects/Autojob-search/','/home/saunalserver/projects/shortlist/pipeline/') WHERE output_folder LIKE '/home/saunalserver/projects/Autojob-search%';` (all 10 targets verified present on disk). `rm -r pipeline/output/2026-09-02` after eyeballing.
6. **Normalize `posted_at` in the two offending source adapters** (weworkremotely RFC-2822, jobbank "August 13, 2026" → `email.utils.parsedate`/`dateutil` → ISO date). 136 rows; expiry-by-posted-date silently skips these today.
7. **One partial index for the dashboard's hot filter**: `CREATE INDEX idx_jobs_user_action ON jobs(user_action) WHERE user_action IS NOT NULL;` — currently a full scan. (Skip `posted_at`/`run_id` indexes; 26k rows.)
8. **Policy decision, low urgency**: flip `status` when `user_action` is set (or a statusless "triaged" view), so "queued" means actionable. Today 593 of 829 queued rows are already decided and only 236 are live — 176 of those are >2 weeks stale score-7s.
9. Optional hygiene: periodic `PRAGMA wal_checkpoint(TRUNCATE)` after the 19:00 run if the WAL bothers you (8.7 MB is fine); delete the stale 17 MB `autojob.db.bak-2026-09-02` once a fresh `.backup` exists (file-copy of a live WAL DB is unsafe — use `sqlite3 '.backup'`).

**Skipped**: per-column page accounting beyond description, index tuning beyond #7, and normalizing the Z-vs-+00:00 timestamp cosmetics — measurable win ≈ 0 at this scale.
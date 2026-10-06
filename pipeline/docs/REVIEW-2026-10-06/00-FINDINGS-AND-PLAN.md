# Shortlist Review 2026-10-06 — Combined Findings & Plan

Synthesis of the six observation reports in this folder (01–06, produced by parallel
read-only agents, 2026-10-06). Nothing has been changed yet — every item below is a
finding or a proposal. Numbers come from the reports; see each report for the SQL/code
evidence. Small cross-report discrepancies noted at the end.

---

## Part 1 — Findings

### 1.1 The headline: this is not a supply problem, it's a throughput problem

- The funnel queues **16.1 jobs/day** since the 09-28 expansion (was 6.6/day before).
  Victor's lifetime consumption: **0.55 applies/day**, in bursts (~1 session/week,
  30–50 decisions/hour when he shows up).
- **121 jobs have already expired unreviewed** — every single one `user_action IS
  NULL`, 102 of them scored 7+. That is the largest measured loss of good jobs in
  the system, bigger than all prefilter false negatives combined. The next cohort
  of early-September queue rows hits the 45-day `fetched` expiry around
  **2026-10-18**.
- The "829 queued backlog" is a bookkeeping artifact: **593 of those rows are
  already decided** (status never flips on user action). The live backlog is
  **236** (230 @7, 6 @8) — and **76% of it is older than 14 days**.
- Proven decay curve: applies happen at **1.5 d** median after scoring; dismissals
  at 3.0 d; **nothing unreviewed after ~6 days has ever been applied** (max apply
  latency 5.7 d, 16/18 applies within 4 d). So ~144 of the 236 backlog rows are
  provably dead weight waiting to expire.

### 1.2 What actually separates Apply from Dismiss (report 01)

18 applies vs ~240–290 deliberate dismissals (only true bulk = the 301-row SQL wipe
on 09-12; the 71-dismissal session on 10-05 was a real 2.5 h review with 8 applies
interleaved — discrimination is per-job, not per-session):

1. **Systems-building day-to-day vs coordination/care work.** Applies: GTM
   Automation, AI Automation Engineer, Partner Ops, Business Strategy Analyst.
   Same-session dismissals at the same score: "Patient Intake Coordinator",
   "Accreditation Associate". The title family is identical; the *duties* differ.
2. **AI as the product/mission, not a buzzword.** The scorer's "+1 mentions
   automation" fires on 78% of *both* groups — it can't tell "you'll build the
   automation" from "we use computers".
3. **Early-career bands (1–4 yrs) at small/mid product companies.** Zero applies to
   edu/gov/nonprofit/large enterprise (0/18 vs 17/290 dismissals); zero to
   support/CX-titled roles (1/18 vs 24/290).
4. **Complete, verifiable postings.** 0/18 applies had `low_confidence` or
   truncation flags; 51 snippet-only + 12 low-conf dismissals. That class has
   **never converted, ever** (0/41 reviewed).
5. **Freshness** (see 1.1).

What the score never captures but Victor clearly acts on (all present verbatim in
dismissed jobs' `gaps` text): phone-based work, field/physical duties, commute
burden, employer sector, shift hours, hidden employer, truncated data.

### 1.3 The score is currently a coin flip (report 06)

- AUC of `fit_score` predicting apply: **0.858 pre-09-28 → 0.519 post-09-28**.
- Since the paid-first chain (09-29), **zero 9–10 scores exist** (nemotron-lightning
  max = 8 across 1,636 scores) — the historically best band (3/4 = 75% apply rate)
  is unreachable. All 6 remaining 9–10s in the queue are pre-0928 leftovers.
- 7 vs 8 — the only distinction the queue sorts on — now predicts nothing:
  6.6% vs 7.6% apply rate post-0928.
- **4.5× queue-rate gap between models** (ultra:free 1.7% vs lightning 7.7% on
  adjacent days, same config): the same posting's fate depends on which model was
  first healthy that run. v1's model-picked score makes this unfixable by config.
- The **v2 fact-based scorer is fully built and dormant**: `scoring.version: 1`,
  `score_facts` has **0 populated rows**, `eval_scorer.py` exists with 328 offline
  labels showing v2 AUC 0.809 vs v1's live 0.519–0.683. v2's fact taxonomy
  (`role_family` incl. call_center/trades, `employer_type` incl. public_sector/
  agency_or_hidden, `people_manager`) encodes exactly the separators in §1.2.
- Prompt criteria contradicted by behavior: manager-titled roles convert fine
  (4/18 applies), one apply was a US-based employer, one a hybrid in Hamilton ON —
  yet the prompt DQs USD-comp and penalizes manager seniority.
- The reasoning prose is useless for triage: 100% of applies and 85% of dismissals
  read "Strong fit / no hard disqualifiers".

### 1.4 Two verified prefilter bugs are killing the exact supply you asked for (report 05)

- **Bug A — `"Remote, CA"` parsed as California** (`prefilter.py:113-114`): the
  boards remote-Canada pass writes exactly this string; **all 281 such rows were
  prefiltered, 0 ever scored**. The pass delivers zero jobs while costing 40
  queries × 35 results per run. Victims include remote-Canada ops roles at
  Mimecast, Element Fleet, Smile CDS.
- **Bug B — `remote is True` vs SQLite int 1** (`prefilter.py:95`): the source
  remote flag never counts as remote wording. **504 remote-flagged jobs killed by
  deny-city rules** (toronto 191, montréal 59, calgary 52…), ~20% of a sample
  clearly target-family (CIBC Business Systems Analyst, Instacart Billing Ops).
- **Supply-chain title words eat their own queries**: `planner` (28% FN), `buyer`
  (36% FN), `scheduler` (20% FN) — ~33 clear false negatives in the family the
  09-06 queries were added for. Generic noise words (senior/representative/
  operator) are ~96% correct.
- Overall prefilter FN ≈ 2.5–3% — high precision, but the misses cluster in
  remote-Canada and supply-chain, i.e. the newest, most-wanted supply.

### 1.5 Code bugs (report 03)

| Severity | Bug | Fix |
|---|---|---|
| High | **Test suite is red right now** (1 failed/125) — wall-clock time-bomb in `test_expiry.py`, red since ~09-30; **no CI exists** to notice | inject clock into `expire()` + add pre-push hook or GHA (ruff+pytest) |
| High | **Scrape phase holds one write txn up to ~15 min, 2×/day** (`pipeline.py:185-201` commits once after the loop) — dashboard Apply/Dismiss clicks can hit `SQLITE_BUSY` exactly during the evening review window | commit per scrape (1 line) |
| Med | **Digest re-lists acted + carry-over jobs**: no `user_action IS NULL` filter, window bound to prev run's `started_at` (run 80's digest: 17 re-shows + 1 already-dismissed; the 10-05 bulk-dismissed reappeared in that evening's digest) | 2 one-line changes |
| Med | No circuit breaker on total LLM failure → provider-down grinds a run to the 8 h systemd cap | stop after ~10 consecutive `res is None` |
| Med-Low | Worker `docs` subprocess consumes the run's abort flag | guard abort check |
| Low-Med | Zombie runs #22 and #53 stuck `running` forever | startup sweep, 1 line |
| Low-Med | Fetchers swallow HTTP errors → dead sources invisible (eluta 0-job run, `error=NULL`; `source_runs.error` literally never populated) | flag zero-fetch streaks |
| Low | `claim_next_command` not atomic (latent — single poller today) | guarded UPDATE |

The 2.4.0 paid-first chain itself is **sound**: server-side quota probe, no
miscount, no money burn; empty completions gone; ruff clean; cost ~$0.03–0.06/run
while the 1,000/day free bucket expires unused. Money is not the constraint —
review attention is.

### 1.6 Data hygiene (report 02)

- Dedupe is airtight: 0 duplicate fingerprints in 26,398 rows. Cost of imperfect
  title+company matching: 123 redundant LLM calls (~1.3%) + a few double-queue
  entries (JYSK ×5). Negligible.
- 109 MB DB, **58% is description text on dead rows** (prefiltered/skipped) that
  nothing will ever read → NULL-out + VACUUM → ~45 MB.
- 10 `output_folder` rows point at the pre-move repo path; 44 orphan folders from
  the 09-02 reset; 136 unparseable `posted_at` (weworkremotely RFC-2822, jobbank);
  serper counter undercounts (817 tracked vs ~2.8 k theoretical burn).

### 1.7 Dashboard & ops (report 04)

- Review loop is **5 clicks/job, zero keyboard shortcuts, no auto-advance**; no
  bulk UI (the one bulk dismissal was raw SQL); `score_facts` never displayed.
- Apply has **no server-side idempotency guard**; tracker insert runs *before*
  `setUserAction` (half-failed apply → duplicate row on retry); handler without
  try/catch can wedge the buttons on "Applying…".
- Worker healthy but has executed 1 command ever; `fetchPendingCommands` exists and
  is displayed nowhere (worker-down = silent stall).
- **Backups are weekly (Mon 05:00) only** — the entire 10-05 evening session (8
  hand-picked applications, the project's most valuable rows) is in **no backup**.
  RPO if the disk dies: up to 7 days. The correct `sqlite3 '.backup'` pattern
  already exists in the backup script; shortlist just was never added.
- Tracker is frozen: all 18 rows `status='applied'`, `next_action` NULL,
  `companies` empty → check-reminders nags everything at 14 d; no outcome signal
  exists to tune anything against.

### 1.8 Source economics (report 05)

- Best per-LLM-call: **ats_companies** (7.1% queued @ 3.6 LLM/queued — 3× better
  than boards, underused: ~120 hand-listed slugs vs 823 discovered boards), **eluta**
  (15.2% queued, snippet-only), **wttj** (1 apply from 25 jobs — best applied/new),
  **remoterocketship** (12.5% queued). **serper** best fetch-uniqueness (53%).
- Dead weight: **amazon** (18 k fetches → 4 queued → 0 applied, 16 LLM/queued),
  **jooble** (60 req/day against a 500-lifetime key for ~2% new, 0 applied, last
  queue contribution 09-15), **workday** (0 applies from 1,292 jobs, 15.2
  LLM/queued), **hn** (30 LLM/queued).
- The 9 new 09-28 sources: 130 jobs, 1 queued-relevant outcome (wttj apply) in
  8 days. Early — but the expansion so far added volume, not quality.

---

## Part 2 — The plan

Ordered by dependency and leverage. Items 1–8 are one-afternoon fixes; 9–14 build
the feedback loop; 15–19 are the scoring rebuild. Nothing here adds a single new
source until the review loop can digest what already arrives.

### Phase 0 — stop the bleeding (each item ≤ 1 h, mostly one-liners)

1. **Fix prefilter Bug A + Bug B** (2 lines), then requeue the mis-killed rows
   (`status='new'` for the 281 `Remote, CA` + the ~100 clearly-relevant
   remote-flagged victims — they'll be re-scored next run at ~$0.0003 each).
   *Effect: un-bricks the remote-Canada pass; est. +25–40 queued-equivalents of
   best-policy-fit supply.*
2. **Auto-demote unreviewed queue entries older than 14 days** (dashboard default
   filter + digest exclusion). *Effect: −76% of the visible backlog instantly,
   ~0 historical apply loss (nothing >6 d old has ever converted). Makes "To
   review" a real number.*
3. **Fix the digest window bug** (acted filter + `finished_at` boundary). *Effect:
   no re-shows of dismissed jobs, no double-listed runs.*
4. **Commit per scrape** (1 line). *Effect: closes the only window where Apply/
   Dismiss can fail with SQLITE_BUSY — during evening review.*
5. **expire() clock injection + green the test + add CI** (pre-push hook or GHA:
   ruff + pytest). *Effect: never ship a silently red suite again.*
6. **Daily consistent backup of both DBs** (`sqlite3 '.backup'` into the existing
   backup path + a small timer). *Effect: tracker RPO 7 d → 1 d. This is the
   single cheapest critical fix in the project.*
7. **Supply-chain title carve-out**: allow `planner|buyer|scheduler` when combined
   with supply/demand/procurement/logistics/inventory words (~10 yaml lines).
8. **Prune dead weight**: disable or slash `amazon` and `jooble`; keep
   `ats_companies`, `wttj`, `remoterocketship`, `eluta`, `serper` fed.

### Phase 1 — make review fast and make decisions into data

9. **Keyboard-driven review**: j/k navigate, `a` apply, `d` dismiss, auto-advance
   to next pending. *Observed pace 30–50 decisions/h at 5 clicks; plausible 2–3×.*
10. **One-tap dismiss reasons** (6–8 chips: role-family / seniority / phone-field /
    commute-onsite / employer-type / bad-data / stale). Single write point already
    exists (`dismissPipelineJob`). *This is the dataset everything in Phase 2
    tunes against — without it, every recalibration is vibes.*
11. **Demote low_confidence/snippet-only jobs** out of the digest (0/41 lifetime
    applies; optionally force a scrape before queueing them at all).
12. **Expiry pressure visible**: "N pending jobs retire before the next digest"
    line + expiring-soon badge. *(+ the Phase-0 backup item covers the other ops
    risk.)*
13. **Apply idempotency + unwedgeable UI**: server-side guard on
    `user_action IS NULL`, unique index on `applications.posting_url`, try/catch
    in the handlers.
14. **Tracker outcome loop**: quick status moves (screening/rejected/ghosted) —
    even a weekly 2-minute bulk update; populate `companies`; wire
    `applications.source` to the pipeline source.

### Phase 2 — scoring that discriminates

15. **Flip `scoring.version: 2`** after running `eval_scorer.py` against real
    labels; retune the threshold for the v2 band. *Effect: scores become
    model-independent (kills the 4.5× calibration gap), facts get recorded
    (`score_facts`), and the fact taxonomy already encodes §1.2's separators.
    Offline eval: AUC 0.809 vs live 0.519.*
16. **Restore the 9–10 ceiling** (v2 weights or anchors): the only band with >50%
    apply rate is currently unreachable.
17. **Prompt cleanup in the same pass**: drop the USD-comp DQ and the manager
    penalty (contradicted by applies); require discriminating one-liners (salary
    band, seniority, industry, role family) instead of "Strong fit".
18. **Company blocklist**: ≥2 deliberate dismissals of the same company → auto-skip
    its future postings (27 known offenders: sailor health ×6, roylo ×4, jobber
    ×4, UBC ×3…).
19. **Composite digest ranking**: score + source prior + freshness decay − company
    history; surface top-N by expected apply instead of score-desc top-15.

### Explicitly rejected by the data

- **Raising the threshold 7→8**: loses 4/10 post-0928 applies (all @7). **Lowering
  7→6**: buys a band with 0 lifetime applies. **7 stays.**
- **More sourcing**: 16.1 queued/day vs 0.55 consumed/day. Any new source now
  strictly increases the unreviewed-expiry loss rate. Revisit only after Phase 1.
- **Free-first LLM**: saves ~$0.06/day at 3 s/job latency and empty-completion
  risk. The paid-first tradeoff is correct; revisit if the credit horizon matters.
- Rescoring/rewriting historical rows (moot once v2 lands; the eval harness uses
  offline labels).

---

## Part 3 — Decisions only Victor can make

1. **US-remote policy**: `deny_us` killed 307 US-remote-flagged jobs. If US remote
   is genuinely acceptable, it's the largest untapped pool (1 flag + 1 pass). If
   not, no change.
2. **Requeue scope** for the prefilter-bug victims (all ~800 vs the ~100–150
   clearly-relevant subset; requeued rows re-score next run).
3. **14-day auto-demote vs auto-expire** for unreviewed queue entries (demote is
   reversible and my default; expire matches the observed decay curve harder).
4. **Edu/gov/nonprofit**: 0/18 applies vs 17/290 dismissals — hard-block in
   prefilter, or keep scoring them?

---

## Cross-report discrepancies (both benign, noted for honesty)

- Deliberate-dismissal count: 290 (report 01, excludes only the 301-row SQL wipe)
  vs 239 (report 06, excludes all 352 of 09-12 including its 51 interactive
  clicks). Direction of every finding is unchanged.
- Timer times: briefs said 07:00/19:00; actual `OnCalendar` is 06:30/17:30
  America/Vancouver (report 04) — CONTEXT.md drift, worth a one-line fix.

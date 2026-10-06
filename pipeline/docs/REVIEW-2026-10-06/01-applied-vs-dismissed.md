# Applied vs Dismissed — What Separates Victor's Applies from His Dismissals

**Repo:** `/home/saunalserver/projects/shortlist` · **Data:** `pipeline/data/autojob.db` (26,398 jobs), `dashboard/data/jobsearch.db` (18 applications) · **Read-only review, 2026-10-06** · **Git HEAD:** 877686c (v2.4.0)

---

## 1. Dismissal session classification: BULK vs DELIBERATE

591 dismissals total. Timestamp clustering (gap analysis via `LAG()` over `user_action_at`, millisecond precision) splits them cleanly:

| Date | Session window | Count | Scores | Avg gap between actions | Verdict | Confidence |
|---|---|---|---|---|---|---|
| 2026-09-04 | 22:30–22:32 | 3 | 8 | ~65 s | Deliberate | High |
| 2026-09-05 | 01:57–03:00 | 48 | 6–8 | 20–78 s (sub-bursts) | Deliberate (rapid triage) | High |
| 2026-09-06 | 18:03, 18:31 | 4 | 7 | ~36 s | Deliberate | High |
| 2026-09-07 | 00:55–01:25 | 14 | 6 | ~33 s | Deliberate | High |
| 2026-09-08 | 18:07, 21:24, 23:03 | 24 | 7–9 | 13–31 s | Deliberate | High |
| 2026-09-09 | 20:26, 22:30 | 16 | 8 | 17–37 s | Deliberate | High |
| **2026-09-12** | 00:06–00:19 | 24 | 8–9 | ~34 s | Deliberate | High |
| **2026-09-12** | 01:36–01:59 | 24 | 8 | ~23 s | Deliberate | High |
| **2026-09-12** | **03:51:07.873 (single instant)** | **301** | **all 6** | **0 s — all 301 rows share one millisecond timestamp** | **BULK (programmatic)** | **Certain** |
| 2026-09-12 | 20:07–20:08 | 3 | 8 | ~23 s | Deliberate | High |
| 2026-09-28 | 18:06–18:22, 19:11 | 45 | 7–8 | 12–20 s | Deliberate (stale-backlog sweep, avg 9.9 d since scored) | High |
| 2026-09-29 | 21:16–21:18 | 2 | 8 | ~2.5 min | Deliberate | High |
| 2026-10-03 | 18:29–18:37 | 11 | 8 | 17–34 s | Deliberate | High |
| **2026-10-05** | 18:38–21:01 | 71 | 7–8 | 1.8–26 s (sub-bursts) | **Deliberate** — 8 APPLYs interleaved within the same session | Certain |
| 2026-10-06 | 17:30 | 1 | 8 | — | Deliberate | Certain |

**Verdicts on the suspected dates:**
- **2026-09-12 (352):** 301 are one programmatic bulk wipe of unreviewed score-6 jobs (all share the exact timestamp `2026-09-12T03:51:07.873Z`, status still `queued`) — this is the post-recalibration cleanup after `min_score_to_queue` went 6→7 (`pipeline/config/search.yaml:58`). The other 51 that day were interactive review at 8–9.
- **2026-10-05 (71): NOT bulk.** Distinct millisecond timestamps, 1.8–26 s apart, and — decisive evidence — the session contains 8 of the 18 total APPLYs interleaved between dismissal bursts (e.g. APPLY `Operations Manager (BC)` 18:45:08, dismiss 18:45:31; APPLY `Partner Ops @ Super.com` 19:29:53, dismiss 19:33:27). This is one long discriminating review session, not a sweep.
- **2026-09-28 (45) and 2026-10-03 (11): NOT bulk.** Same signature: distinct timestamps, 12–34 s gaps, real reading pace. The 09-28 group averaged 9.9 days since scoring — a deliberate purge of the backlog that accumulated while the 9 new sources were being wired up.

Cross-check: the repo's own eval harness uses the same discriminator (`BULK_MINUTE = 20` dismissals/minute, `pipeline/scripts/eval_scorer.py:35`). Outside the 03:51 instant, the busiest minute anywhere is 9 dismissals — nothing else crosses the bulk line.

**Working sets from here on: 18 applied vs 290 deliberate dismissals** (301 bulk excluded from "judgment" comparisons).

---

## 2. The comparison dataset: 18 applies vs 290 deliberate dismissals

### 2.1 Score

| Score | Decided | Applied | Dismissed | Apply rate |
|---|---|---|---|---|
| 10 | 1 | 1 | 0 | 100% |
| 9 | 5 | 2 | 3 | 40% |
| 8 | 186 | 11 | 169 | **5.9%** |
| 7 | 337 | 4 | 103 | 1.2% |
| 6 | 316 | 0 | 316 (301 bulk) | 0% |

The score's job is to protect review time, and above 7 it does gate correctly (0 applies ever at ≤6 confirmed — the 09-12 recalibration was right). But **within the queue the score barely separates anything**: the 8-band contains 169 dismissals and 11 applies. Almost all discrimination happens in Victor's head, post-score. Notably `search.yaml:63` records this exact finding for v1: "139 jobs at 8 → 5 applied, 129 dismissed."

### 2.2 Freshness (the strongest numeric separator found)

| Latency | Applied (n=18) | Deliberate dismissed (n=290) |
|---|---|---|
| scored_at → user_action_at | **1.48 days** | **2.97 days** |
| fetched_at → user_action_at | 1.74 d | 3.14 d |
| posted_at → decision (where known) | 6.3 d (n=10) | 7.4 d (n=193) |

Applies are decided at half the age of dismissals. The 09-28 sweep (9.9-day-old backlog) produced 45 dismissals and 0 applies; every apply except FISPAN happened ≤3 days after scoring. Stale queue items almost never convert — they get swept.

### 2.3 Data quality (second strongest)

| Signal | Applied | Deliberate dismissed |
|---|---|---|
| `low_confidence = 1` | **0 / 18** | 12 / 290 |
| Description ≤600 chars (snippet-only) | 2 / 18 (11%) | 51 / 290 (17.6%) |
| Avg description_length | 3,486 | 3,092 |
| Gaps text mentions truncation/"unclear"/"snippet"/"not fetched" | **0 / 18 (0%)** | 35 / 290 (**12.1%**) |

Zero applies came from low-confidence or truncation-flagged postings. Every one of those jobs that reached review got dismissed.

### 2.4 Source, model, location — weak or no separation

- **Source:** apply rates among decided jobs — wttj 1/4, serper 4/42 (9.5%), ats_companies 2/21, adzuna 2/32, boards 6/131 (4.6%), himalayas 2/49, workday/jooble/eluta 0 combined (0/21). serper + ats_companies (the curated/career-page fetchers) are ~2× boards.
- **Scorer model:** paid `nemotron-3.5-lightning` 9/92 (9.8%) and `gemini-2.5-flash-lite` 2/15 vs free `nex-n2.5-mini` 2/82 (2.4%) and `minimax-m2.7` 4/77 (5.2%). Small n, but directionally supports the paid-first switch made in 877686c.
- **Location/remote:** applied = 6 remote / 6 on-site Vancouver / 6 elsewhere-Canada; dismissed = 110 remote (38%) / 90 Vancouver (31%) / 90 other-Canada (31%). Nearly identical — location is a prefilter concern, already handled upstream; it does not drive the apply/dismiss margin.
- **Employment type / salary:** employment_type present in 13/18 applies vs 211/290 dismissals; salary fields present 4/18 vs 37/290. No separation (both mostly absent).
- **Review latency by model/day:** normal days run <1.5 d scored→action; the two sweeps (09-28: 9.9 d, 10-05: 3.6 d) inflate the dismissed average.

### 2.5 Title & employer patterns

Title buckets: applied = 10 ops/analyst, 4 with Manager in title, 3 "Sales Ops" (all genuinely ops), 1 engineer-titled (AI Automation). Dismissed = 154 ops/analyst, 69 senior/mgmt, 28 other, 16 marketing, 11 sales, 7 eng, 5 healthcare. Title family alone doesn't separate — **the day-to-day under the title does** (see §5).

Employer type (keyword classification): edu/gov/nonprofit employers — **0/18 applies vs 17/290 dismissals** (Langara College, FDU, CPSBC, PHSA, Canadian Cancer Society ×2, Food Banks Canada, BC Soccer…). Support/CX-titled roles — 1/18 applies vs 24/290 dismissals.

### 2.6 Reasoning text (read in full: 18/18 applies; 90+ deliberate dismissals sampled across every session and score band)

Both groups get near-identical "Strong fit, recommend" prose from the v1 scorer (anchor: "7–8: Strong fit, recommend", `pipeline/prompts/scorer.md:117-118`) — 78% of both groups mention automation/AI in strengths, ~40–44% of both groups carry years-of-experience gaps. **The prose does not encode the decision.** The discriminators live in details the score doesn't weigh (§5).

---

## 3. Tracker cross-check (`dashboard/data/jobsearch.db`)

- **18 applications, 18 pipeline applies — URL sets are byte-identical** (diff of `jobs.url` vs `applications.posting_url` = empty). No missing, no orphans, no URL drift.
- Every tracker row: `status='applied'`, `date_applied` matches the pipeline `user_action_at` date, `tags=['autojob', <source>]`, notes carry `Autojob (score N/10). <fit_reasoning>` — written by `promoteJobToTracker` (`dashboard/actions/autojob.ts:80-95`).
- **No outcomes exist:** all 18 still sit at `applied`; `next_action`/`next_action_date` null everywhere; `companies` table is completely empty (0 rows). Nothing records interview/rejection/silence, so there is no feedback signal on whether applies convert.

---

## 4. Misfires

1. **The 8-band is the misfire zone:** 169 deliberate dismissals at score 8 vs 11 applies — a 15:1 dismissal ratio under a "Strong fit, recommend" anchor. Not all are scoring errors (many are legitimate "not for me"), but three sub-groups are clearly scorer failures:
   - **Snippet-only / truncated-JD postings scored 8:** 51 snippet-only (≤600 chars) and 12 `low_confidence=1` dismissals, e.g. `Intelex RevOps Specialist` (desc_length 0, low_confidence, s8), 6 adzuna 500-char snippets on 09-28 alone. Zero applies ever came from this class.
   - **Hidden-employer postings:** both non-bulk score-**9** dismissals were these — Jobgether EIR ("The hiring company is an unnamed partner"), Power Digital via aggregator ("posting does not specify location or employment type"). A 9 with no verifiable employer is noise.
   - **Fake-junior senior/support roles:** CSM roles wanting 3–5 years (`Netomi`, `Thanx` enterprise $3–6M ARR), Chief of Staff at 4+ years, Amazon Software Development Manager (also an LMIA work-auth mismatch the JD-level scorer missed).
2. **Applied at low scores: none.** Minimum apply score is 7 (4 of them: FISPAN, PosiTrace, EarthDaily, Monachus). The 6→7 recalibration was validated by behavior; a 7→8 move is *not* supported — 4 of 18 applies (22%) came at exactly 7.
3. **Dismissed-then-refetched: zero.** No fingerprint appears more than once in 26,398 rows; no dismissed job ever re-entered the queue. Dedup (fingerprint + seen_urls) is airtight as built.
4. **Docs-before-decision waste:** 12 jobs got tailored docs generated and were then dismissed (all 2026-09-03→09-05, all score 8 — KultreMedia, Harbor, Topcon, Aloplay, Koronet, Spotter Labs, Elation, Acuity sibling, Belltower, Netomi, Beedie, StackAdapt). Victor self-corrected behaviorally: since 09-05, docs are generated almost only post-decision (only 4 applies carry `docs_generated`). The UI still permits the wasteful order.
5. **Session-09-28 nuance:** 45 dismissals of a 9.9-day-old backlog right after 9 new sources went live — not a scoring misfire but a queue-hygiene one: the pipeline let two weeks of queue rot before review, and rot never converts (§2.2).

---

## 5. Synthesis: what actually predicts an Apply

Reading all 18 applies against 90+ dismissals, the apply signature is:

1. **The day-to-day is building/running systems, not administering people or paperwork.** Applies: ZayZoon "GTM Automation Specialist" ("requires 1-2 years… automation, workflows, data hygiene, and dashboards"), 7shifts "AI Automation Engineer" ("focus on AI, LLMs, and automation tools (n8n, Zapier, Make)"), CoLab "Business Strategy Analyst", Super.com "Partner Operations". Same-session dismissals at the same score 8: "Accreditation Associate", "Patient Intake Coordinator", "Provider Support Coordinator", "Enrolment Services Advisor" — coordination/care-work, not systems work.
2. **AI is the product or the mission, not a buzzword.** Acuity Insights (score 10, "explicitly encourages automation/AI input"), Clipboard ("AI-native ops generalist… YC-backed"), CanadaVisa "Operations Associate (Legal AI)", Monachus "AI Enablement". The scorer's +1 "mentions automation" fires equally on dismissals (78% of both groups) — it can't tell "you'll automate the workflow" from "we use computers".
3. **Genuinely early-career bands (1–4 yrs) at small/mid product companies.** Hiive "new graduates", inecta "2-year floor", Super.com "1-4 years". Zero applies to edu/gov/nonprofit/large-enterprise employers; 17 such dismissals.
4. **Verifiable, complete postings.** 0 applies with low_confidence or truncation-flagged gaps; 12% of dismissals had them.
5. **Freshness.** Applies decided 1.5 d after scoring vs 3.0 d for dismissals. He applies from the top of the digest; leftovers get swept.

**What Victor acts on that the score does not capture** (all present verbatim in `gaps` text of dismissed jobs, none reflected in the number): phone-based work ("Role is specialized phone-based retention" — Jobber), field/physical duties ("driving large vehicles and travel in mountains" — RUX; "50% travel across Canada" — QHR), commute/onsite burden (Burnaby in-person — LH Home), employer sector (real estate — Beedie; corrugate boxes — Great Little Box), shift hours (10am–7pm — Jobber), hidden employer, and truncated data. The scorer extracts these as prose and then doesn't penalize them — a "moderate gap" costs 1 point (`prompts/scorer.md:124-131`), leaving a call-center-adjacent or field role at 7–8.

The 10-05 interleaved timeline proves the discrimination is per-job, not per-session: at 19:19–19:21 he dismissed 14 consecutive score-8 healthcare-admin/CSM roles in ~90 seconds of clicks, then at 19:29 applied to Super.com Partner Ops at the same score.

---

## 6. Improvement ideas (ranked: impact vs effort)

| # | Idea | Impact | Effort | Evidence |
|---|---|---|---|---|
| 1 | **Capture a dismiss reason at click time** — one-tap tags on the Dismiss button (role family / too senior / phone-field / commute-onsite / employer type / stale / bad data), stored in a new column. Single write point already exists (`dismissPipelineJob`, `dashboard/actions/autojob.ts:102-109`; `setUserAction`, `dashboard/lib/autojob-db.ts:232-233` writes only action+timestamp today). | **High** — converts 290 existing + future decisions into structured labels; this is the dataset that tunes everything below | **Low** | §5: the discriminators are nameable in 6–8 tags; they're currently only implicit |
| 2 | **Enable the v2 fact-based scorer** (`prompts/scorer_v2.md` is written, `search.yaml:63` still says `version: 1`) after running `scripts/eval_scorer.py` against real labels. v2 already encodes the exact separators found: `role_family` incl. `call_center`/`trades_field_physical`, `duties_match`, `employer_type` incl. `public_sector`/`agency_or_hidden`, `people_manager`. | **Highest** — attacks the 169-dismissal 8-band directly | Medium (built; needs eval + threshold re-tune) | §2.1, §4.1; config comment already concedes v1's 8-band failure |
| 3 | **Don't queue snippet-only/low-confidence postings at 8** — cap snippet-scored jobs at 7 (or a distinct badge in the review UI). | High | Low | §2.3: 51 snippet-only + 12 low_conf dismissals; 0 applies from that class |
| 4 | **Hard-downscore hidden-employer/aggregator postings** (v2's `agency_or_hidden` → strong penalty, e.g. max 6). | Medium | Low | §4.1: both score-9 misfires were hidden-employer |
| 5 | **Freshness-aware review surface** — sort/badge the queue by scored-age; auto-expire or drop-priority on >5-day-old unreviewed items. | Medium | Low-Med | §2.2: applies at 1.5 d vs dismissals at 3.0 d; the 09-28 sweep was 9.9-day-old stock, 0 applies |
| 6 | **Outcome tracking in the tracker** — use the existing `status` lifecycle and populate `companies`; even weekly bulk updates. | Medium (closes the loop: are the 18 applies converting?) | Low | §3: all 18 frozen at `applied`, `next_action` null, companies empty |
| 7 | **Gate docs generation behind a decision** (hide the docs button until user_action is set). | Low | Trivial | §4.4: 12 docs-then-dismissed in the first week; behavior already self-corrected |
| 8 | Add a one-line "why" chip row (from v2 facts) in the review list, since the default sort is `fit_score DESC` (`autojob-db.ts:190,217`) and within the 8-band the score provides zero ordering. | Medium | Low | §2.1, §5 |

Skipped: any re-scoring/rewrite of historical rows (write ops, out of scope); dedup changes (already perfect — 0 duplicate fingerprints in 26,398 rows).

---
# Slice 6 — Scoring & Ranking (observation report, 2026-10-06)

Read-only analysis. All DB queries via `mode=ro` URIs on `pipeline/data/autojob.db` (no writes anywhere). n is small (18 applies) — treat rates as directional, exact counts as fact.

---

## 1. Predictive power of fit_score

### 1.1 Dismissal classification (which dismissals are signal)

Total: 18 applied, 591 dismissed. Hourly clustering + inter-action gaps:

| Session | Count | Scores | Pace / gaps | Classification |
|---|---|---|---|---|
| 2026-09-12 (00:00–03:xx, continuous) | **352** | 301×6, 49×8, 2×9 | 306 of 351 gaps ≤5 s; 301 @6 = clearing the pre-recalibration backlog after min_score 6→7 (search.yaml:58) | **BULK — excluded everywhere below** |
| 2026-09-05T02 | 48 | 9×8, 38×7, 1×6 | ~1 per 75 s | rapid triage — kept |
| 2026-09-28T18–19 | 45 | 33×8, 12×7 | 2 s–3 min, bursts 2–10 s | shallow triage (title + one-liner depth) — kept, flagged shallow |
| 2026-10-03T18 | 11 | 11×8 | gaps 1–8 s | shallow triage — kept |
| 2026-10-05T18–21 | 71 | 26×8, 45×7 | bursts of 2–4 s (6 dismissals in 14 s at 19:21) | shallowest triage — kept (per-job clicks at 7–8, not a threshold purge) |

Deliberate dismissals = 591 − 352 = **239** (6×15, 7×103, 8×120, 9×1). This matches the codebase's own bulk heuristic (eval_scorer.py:35 `BULK_MINUTE = 20`).

### 1.2 Score separation

Apply rate by band (reviewed = applied + deliberate dismissals):

| Band | Applied | Delib. dismissed | Apply rate |
|---|---|---|---|
| 6 | 0 | 15 | **0%** |
| 7 | 4 | 103 | 3.7% |
| 8 | 11 | 120 | 7.7% |
| 9–10 | 3 | 1 | **75%** (3/4) |

AUC of fit_score predicting apply (Mann-Whitney, tie-corrected):

- All periods: **0.683**
- Pre-2026-09-28: **0.858**
- Post-2026-09-28: **0.519** — collapsed to coin-flip

Post-09-28 within-band: score 7 → 4/61 reviewed applied (6.6%), score 8 → 6/79 (7.6%). **The 7-vs-8 distinction — the only distinction the queue currently sorts on — is now noise.**

Claims check:
- "0 applies ever at ≤7": **no longer true.** 4 of 18 applies are at 7 (FISPAN, PosiTrace, EarthDaily Analytics, Monachus Solutions — all post-09-28). Pre-09-28 it held (min applied score was 8).
- "9–10 apply rate ~50%": was 3/4 = 75% pre-0928, but it's moot — **since the paid-first chain (commit 877686c, 2026-09-29), zero 9–10 scores exist**: nemotron-3.5-lightning max = 8 across 1,636 scores; ultra:free max = 8 post-09-28. The historically best-predicting band is unreachable by the current chain. The queue's 6 remaining 9-10s are all pre-0928 leftovers.

### 1.3 low_confidence flag vs outcomes

- Reviewed low_confidence jobs: 41 → **0 applied**, 6 deliberate dismissals. Full-description: 18 applied of 568 reviewed.
- Queue rate is identical (low-conf 39/560 = 7.0% ≥7 vs full-desc 596/8,669 = 6.9%) — snippet-only jobs (set when description < 200 chars, scorer.py:19,44,77) cost the same review slots but have never converted.
- 20 low-conf jobs sit in the current unreviewed backlog.

### 1.4 scorer_model per band / chain change

Per-model, post-09-28, adjacent days, same source config — a natural experiment:

| Model | scored | ≥7 | queue rate |
|---|---|---|---|
| nemotron-3-ultra-550b:free (09-28/29) | 590 | 10 | **1.7%** |
| nemotron-3.5-lightning paid (09-30→10-06) | 1,635 | 126 | **7.7%** |

A **4.5× queue-rate gap** between the top two models in the chain (search.yaml:77-78). Whole-history averages: nex-n2.5-mini 4.21 (lenientest), gemini-2.5-flash-lite 3.65, lightning 3.44, minimax 3.16, ultra 2.57 (strictest). Apply/dismiss among acted: lightning 9ap/83dd (9.8%), minimax 4/73, nex-mini 2/30, ultra 1/26, gemini 2/13.

So the 2.4.0 chain did change the score distribution materially: same job, different chain day → different queue verdict ~5% of the time; and no 9–10s ever since.

---

## 2. The scoring stack

### 2.1 What's actually running

- `scoring.version: 1` (search.yaml:64) → **prompts/scorer.md, the model picks the 1–10 score itself.** The entire v2 apparatus exists but is idle in production: scorer_v2.md, `compute_v2` (scorer.py:90-135), the `score_facts` column (**0 rows populated**), and scripts/eval_scorer.py.
- Chain order (search.yaml:77-84): lightning (paid, primary) → ultra:free → deepseek-v4-flash (paid) → laguna-s:free → cohere-north-mini:free → gemma-4-31b:free → openrouter/free. 4 workers.
- Threshold decision: pipeline.py:212,268-270 — `skip` OR `fit_score < min_score_to_queue(7)` → status skipped with reason.

### 2.2 Prompt structure (prompts/scorer.md)

- Step 1 hard DQs (lines 11-89): A seniority (title words; 4+ years in specific domain), B location (on-site outside metro, US-only, residency-pinned remote, **CET-hours**, USD-only comp), C role-type, D tool-as-core-role, E employment-type, F posting-format (**hidden employer**), G must-have vs nice-to-have.
- Step 2 positive signals, +1 each max +3 (lines 92-110): AI/automation keywords, early-career, tool overlap, bilingual French, candidate domain, first-ops-hire, metro/remote-Canada, B2B SaaS/fintech, startup/SMB, US-or-Canada remote, French/EU remote employer.
- Step 3: base 5, penalties for gaps/enterprise, cap 1-10, anchors (lines 113-135). Step 4 decouples skip from score (137-143). 10 calibration examples (145-197).

DQ firing rates (of 8,263 skipped, 6,361 are skip=true): on-site outside metro 219; "JD requires N years" 132; role-type 1.C 82; **CET-hours DQ: fired only 7 times ever** (for 9 new EU sources since 09-28 — surprisingly rare); hidden-employer/aggregator ~277.

### 2.3 JSON robustness (llm.py)

- `parse_json` (llm.py:338-350): strips Gemma `<thought>` blocks and code fences, salvages first `{...}` on decode error, unwraps list→first dict.
- `_try_model` pre-validates JSON (llm.py:255) so a JSON-broken model falls to the next model **without burning the job**; empty completion → next model immediately, no same-model retry. All 7 models fail → job status `error`, retried next run (pipeline.py:264-266). Post-09-28 errors: 0–5 per run of ~130-190 scored. Malformed-but-parseable output degrades to `fit_score` clamp/default 1 (scorer.py:81-83) → auto-skip, silent.

### 2.4 Does the prompt encode what Victor applies to?

Themes in the 18 applies' `fit_reasoning`: bilingual French (4), automation/AI duties (6), remote-Canada (7), entry-level framing (8), B2B SaaS/startup (6), Vancouver-local (7) — **all present in the prompt's Step 2.** The positive-signal side is well calibrated.

Criteria in the prompt with **no evidence of mattering** (or evidence they're wrong):

- **Manager/seniority penalty**: 4 of 18 applied titles contain "Manager" (Operations Manager BC, Client Success Manager, Associate Project Manager, Project Manager). The v1 prompt gives no manager bonus and v2 weights penalize (seniority manager −1, people_manager −2). Reality: manager-titled roles convert fine.
- **"Compensation in USD with no Canadian entity" DQ** (scorer.md:42): the PosiTrace apply's own one-liner cites "US-based employer" as acceptable.
- **On-site outside Vancouver metro as hard DQ**: one apply is a hybrid role in Hamilton, ON ("remote/hybrid model in Hamilton, ON is acceptable" in its one-liner).
- **CET-hours DQ**: 7 firings ever, 0 evidence either way — dead weight or genuinely rare.

Real criteria **missing from the prompt**: the one-liners cannot distinguish classes at all — **100% of applies read "Strong fit/Good fit/Near-perfect" vs 85% of post-0928 dismissals** (49% of dismissals even say "no hard disqualifiers"). Whatever Victor actually discriminates on (salary, company reputation/size in practice, JD detail, competitiveness) is not captured by score or one-liner — it lives in the full JD he reads in the dashboard.

---

## 3. Score stability

- **No rescores exist by design**: URL + fingerprint dedupe, one row per posting, scored exactly once (db.py module docstring; exactly 1 duplicate fingerprint in 26,398 rows). So "score drift across rescores" is structurally N/A — `scored_at` is single-valued per job.
- **Cross-model drift is the live stability issue**: the 4.5× queue-rate gap (§1.4) between ultra:free and lightning means the same posting's queue fate depends on which model was first healthy that run. With fallback models firing on 429s/503s (llm.py cooldown policy), a small random subset of scores is quietly calibrated on a different ruler. v1's model-picked-score makes this unfixable by config; v2's code-computed score (same facts → same score on any model, scorer.py docstring) is the built-in cure.

---

## 4. Ranking

### 4.1 How ordering works today

- **Digest**: `queued_since` → `ORDER BY fit_score DESC, id ASC` (db.py:383-390), top 15 (notify.py:16,74) — pure score-desc, ties broken by insertion order.
- **Dashboard review queue**: default sort `fit_score DESC, fetched_at DESC` (dashboard/lib/autojob-db.ts:186,213-217; app/pipeline/jobs/page.tsx:54), 25/page, hideActioned on.

### 4.2 The real backlog is 236, not 829

`queued` = 829 decomposes: **579 dismissed + 14 applied + 236 never touched** (docs_generated adds 0 unreviewed). Of the 236: 230 @7, 6 @8 (all from 2026-10-06). Age: **76% older than 14 days, 61% older than 21.**

Key timing facts:

- Apply latency (scored → applied): [0.1 … 5.7] days; 16 of 18 within 4 days. **Nothing unreviewed after ~6 days has ever been applied.**
- Median queued → expired = 11.4 days; 121 jobs already expired unreviewed (never seen, ever).

So score-desc sort does exactly the wrong thing: 8s surface and get triaged within a day (median action latency 1.4 d), 7s sink below the fold and rot — 230 of them, of which the 144 older than 21 days are provably dead (max apply latency 5.7 d) and are just waiting to expire.

### 4.3 Ranking inputs available now

- **Source quality priors** (apply rate among reviewed / queue rate per scored): serper 4.7% (8.3% queue), ats_companies 3.8% (28% queue), adzuna 3.4%, himalayas 2.7%, boards 2.3%, jooble/workday/eluta **0 applies**. New sources: wttj 1 apply / 20 scored — best per-scored yield yet; gcjobs, successfactors, workable_search, getro, bcps ≈ 0–92 scored total so far.
- **Negative company history**: 27 companies with ≥2 deliberate dismissals — sailor health ×6, roylo partners ×4, jobber ×4, UBC ×3, ewor gmbh ×3, brex ×3.
- **Remote flag**: reviewed remote-flag jobs 1 apply/42 (2.4%) vs local 3/53 and other/none 6/45.
- **Salary**: only 76/845 (9%) of queue rows carry salary — too sparse to rank on today.
- **Freshness**: posted_at is populated on most sources (expiry already relies on it).

### 4.4 Proposal + queue-reduction estimate

Rank by expected-apply: `rank = fit_score + source_prior + freshness_decay(≤14d) − company_dismissal_count − low_conf_penalty`, surfaced as top-50 weekly digest + dashboard default.

Estimated effect:
- 14-day auto-demote alone: **−180 rows (76%)** from the live view immediately, ~0 historical apply loss.
- low_confidence demotion: −20 current rows, 0/41 lifetime applies.
- Company-repeat auto-skip (≥2 dismissals): would have suppressed ~40 historical re-offenders.
- Net: Victor's weekly review surface drops from 236 stale + ~103 weekly adds to **~50/week ranked**, i.e. ~70-80% reduction in rows ever seen, with all 18 historical applies still inside the top slice (they were all top-band × ≤6 days old).
- Auto-expire is already handled by expiry.py (30 d posted / 45 d fetched, 60 link checks/run) — the gap is only that unreviewed 7s sit in the dashboard for their whole life instead of being demoted at ~10-14 days.

---

## 5. Threshold economics

- **LLM cost is decoupled from the threshold**: every new job gets scored regardless; the threshold only gates queue entry. Marginal LLM cost of lowering it: **$0** (~$0.0003/job lightning; cap 1000 calls/run ≈ $0.30 worst case, search.yaml:74-76).
- **Review time is the scarce resource**: measured triage pace 1.3–2.0 min/job (09-05: 48 jobs/62 min; 09-28: 45/66 min; 10-05: 71/~145 min).
- At 7 (status quo): ~15 queue adds/day (post-0928: 80×7 + 53×8 in 9 days) ≈ 20–30 min/day; yield 10 applies/133 adds (7.5%).
- **7→6**: +16 rows/day (128 sixes scored post-0928, all auto-skipped) ≈ +21–32 min/day for a band with 0 applies ever (0/15 reviewed pre-0928, 0/318 lifetime queue→apply). Not worth it.
- **7→8**: cuts adds 59% but loses 4/10 post-0928 applies (all @7). Not worth it.
- **7 is still right.** The leverage is ranking within the 7–8 band (§4), not the cut point — especially since 7 vs 8 no longer predicts apply (6.6% vs 7.6%).

---

## 6. Improvement ideas, ranked (impact vs effort)

| # | Idea | Impact | Effort | Notes |
|---|---|---|---|---|
| 1 | **Auto-demote unreviewed >14 d** (dashboard default filter + digest exclusion; or expire unreviewed 7s at ~14 d) | High — −76% of backlog instantly, ~0 apply loss (max apply latency 5.7 d) | Low — one WHERE clause in autojob-db.ts + digest filter | Also makes the "829 backlog" number meaningful |
| 2 | **Demote/exclude low_confidence** from digest, sort last | High — 0/41 lifetime applies, 20 dead rows now | Low | Consider not queueing them at all, or forcing a scrape first |
| 3 | **Flip `scoring.version: 2`** (fact-based score computed in code) | High — kills the 4.5× model-calibration gap, makes scores chain-independent and tunable; offline eval already shows v2 AUC 0.809 vs v1 live 0.519-0.683 | Medium — it's fully built (scorer_v2.md, compute_v2, eval_scorer.py, score_facts column idle since schema v3); needs a live soak + threshold retune (v2 band ≠ v1 band) | data/eval/results-v2-off.jsonl: 328 labels already scored offline |
| 4 | **Restore the 9–10 ceiling**: recalibrate anchors (or v2 weights) so lightning-era scoring can emit 9–10 again | High — the only band with >50% apply rate is currently unreachable | Low (prompt anchors) / Medium (v2 weights) | 0 scores ≥9 since 09-29 across 1,636 lightning scores |
| 5 | **Composite digest ranking**: score + source prior + freshness − repeat-company dismissals; top-15 → top-N by expected apply | Medium-high — digest becomes the real triage tool | Low | Source priors from this report; recompute monthly |
| 6 | **Auto-triage negatives**: ≥2 deliberate dismissals of same company → auto-skip its future postings; remote-flag-no-location down-weight | Medium — ~27 known offenders | Low | Needs a "company blocklist" concept, not per-job rules |
| 7 | **Prompt criteria cleanup**: drop USD-comp DQ and manager penalty (contradicted by applies); ask for discriminating facts (salary band, seniority, industry) in the one-liner instead of "Strong fit…" | Medium — one-liners currently can't distinguish 100%-apply from 85%-dismiss text | Low | Do together with #3 |
| 8 | **Stop pre-decision docs**: 12 of 16 docs_generated were later dismissed | Low-medium — saves ultra:free prose calls + reading time | Low | Docs on-demand already; gate the button behind apply-intent |
| 9 | Rescore-sample drift check (eval_scorer.py run monthly vs live labels) | Low-medium | Medium | Detects chain regressions like 09-29 before the AUC does |

**Cheapest big win:** #1+#2 are two filters and reclaim the queue. **Biggest structural win:** #3+#4 together — v2 makes the score model-independent and restores the ceiling the calibration history says matters.

---
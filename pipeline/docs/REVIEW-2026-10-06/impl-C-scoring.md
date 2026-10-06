# Implementation Log — Wave 2 (scoring): make the score discriminate

**Scope:** `pipeline/autojob/scorer.py`, `pipeline/config/search.yaml` (scoring: section only), `pipeline/prompts/scorer_v2.md`, `pipeline/scripts/eval_scorer.py`, `pipeline/tests/`. No commits. No live LLM calls (all tuning ran offline over `data/eval/results-v2-off.jsonl`'s stored facts — zero API spend). `data/autojob.db` only ever read via `mode=ro`.

---

## 1. What was wrong (evidence recap)

- Live v1 AUC collapsed to **0.519** post-0928 (was 0.858) — the 7-vs-8 distinction the queue sorts on is noise.
- **Zero 9–10 scores** in 1,636 paid-chain scores — the only band with >50% apply rate (3/4 historical) is unreachable.
- **4.5× queue-rate gap** between ultra:free (1.7%) and lightning (7.7%) — v1 lets each model pick its own number.
- The v2 apparatus was fully built but dormant at `scoring.version: 1`.

## 2. Method (all offline)

`data/eval/results-v2-off.jsonl` already holds extracted **facts** for all 328 labeled jobs (previous offline ultra:free run). I verified `compute_v2(facts, config_weights)` reproduces every stored score (0/328 mismatches), which makes re-running `compute_v2` with candidate weights a valid, zero-cost tuning loop. I then codified that loop as a new `retune` subcommand in `eval_scorer.py` (see §6) so future tuning never needs API calls either.

Important dataset caveat: `labeled.jsonl` was built 2026-09-28, so it contains only **15 of the 18 applies** (the other 10 post-date it). The 4 manager-titled applies and the US-based PosiTrace apply are NOT in the offline set — their fixes are evidence-based from report 01 and are structurally untestable offline (flagged in §8 for the soak).

## 3. Weight changes and their evidence

| Change | Before | After | Evidence |
|---|---|---|---|
| `seniority.manager` | −1 | **0** | 4 of 18 applies are manager-titled (Operations Manager BC, Client Success Manager, Associate PM, PM — report 01 §2.5). Offline cost: −0.003 AUC alone (0.809→0.806) |
| `people_manager` | −2 (code default) | **removed from config; code default 0** | Same evidence. Offline-neutral: all 19 `people_manager=true` rows already scored ≤4 via other factors. Code default changed so the penalty cannot silently return if the key is absent |
| `implementation_onboarding` | target (base 6) | **adjacent (base 4)** | Offline labels: 1 apply : 12 top-band dismissals — the worst ratio of any target family; "Provider Support Coordinator"/onboarding-specialist class named in report 01 §5 |
| `project_program_coord` | target (base 6) | **adjacent (base 4)** | 0 applies : 8 top-band dismissals offline, 29 hard negatives total — the "coordinator-class" report 01 §5 names as THE separator |
| `family_base.off` | `off: 2` (YAML parsed `off` as boolean `False`, silently falling to the identical code default) | **`'off': 2` quoted** | Cosmetic honesty fix; behavior identical (default was already 2) |
| Everything else (duties_match, years, missing_must_have, signals_cap, employer, senior/lead/executive penalties, all hard DQs) | — | **unchanged** | Duties steepening variants (d1 −2 / d3 +2) raised AUC to 0.822–0.824 but *degraded* within-queue ordering (queue AUC 0.674 vs 0.731) — rejected |

**Deliberately NOT changed:** `bizops_strategy` and `business_systems_analysis` stay target despite 0 offline positives — demoting them added only +0.005 AUC but risks real applies not in the offline set (the CoLab "Business Strategy Analyst" apply is bizops-family; report 01 lists Hiive dashboards work under the apply signature). `public_sector` weight stays 0 — hard-blocking edu/gov/nonprofit is explicitly an open Victor decision (plan Part 3 #4).

### Kept DQs (per instructions, with evidence)
- **Hidden-employer/aggregator**: `employer_type: agency_or_hidden` → hard DQ (both non-bulk score-9 misfires were hidden-employer; report 01 §4.1).
- **CET-hours**: unchanged in the `location_ok` rules (7 firings ever, no evidence either way).

## 4. Prompt changes (`prompts/scorer_v2.md`)

1. **USD-comp DQ dropped** (report 06 §2.4: the PosiTrace apply is explicitly US-based). The `location_ok` US bullet now fires only on **explicit** US-residency restrictions ("US only", named US states, "must reside in the US"); a US-based employer or USD salary alone is not a DQ "unless Canada-based candidates are excluded — do not infer".
2. **one_liner must carry discriminating facts**: role family in plain words + industry/product, years band and salary band if stated, the single biggest pro and con. "Strong fit, recommend" / "Good fit" / "no hard disqualifiers" are **banned** (100% of applies vs 85% of dismissals carried that boilerplate — report 01 §2.6).

Note: the v1 prompt (`scorer.md`) is untouched — v1 goes dormant with the version flip; editing a dead prompt would be unreviewable scope.

## 5. Eval numbers (offline, 328 labels, threshold 7)

| Metric | v1 baseline (stored scores) | v2 old weights | **v2 new weights** |
|---|---|---|---|
| AUC (pos vs hard+easy) | 0.709 | 0.809 | **0.821** |
| Positives kept | 13/15 (87%) | 11/15 (73%) | **11/15 (73%)** |
| Hard negatives below threshold | 51/283 (18%) | 178/283 (63%) | **193/283 (68%)** |
| Easy negatives above | 0/30 | 0/30 | **0/30** |
| Hard ≥9 (top-band noise) | — | 59 | **44** |
| Positive score distribution | — | 10×8, 9×2, 7, 6, 5, 3×2 | **10×7, 9×3, 7, 6, 5, 3×2** |

- **No regression**: AUC up 0.012 vs the shipped v2 baseline, far above live v1's 0.519–0.709.
- **Ceiling restored**: 7 positives reach 10 and 3 reach 9 — the 9–10 band exists again (v1 live: 0 ≥9 in 1,636 scores).
- The 4 dropped positives at t=7: ARC'TERYX (5), GTM Specialist Canada (6), and the two legacy EU residency-DQ'd rows (Luscii "Open application", Finary Care Ops — pre-2026-09-02 era applies DQ'd by the residency rule, kept deliberately).
- The 3 applies not in the labeled set (manager-titled ×4 minus overlap, PosiTrace US-based) are exactly the ones the weight/prompt changes un-block — untestable offline, watch live.

## 6. Threshold retune (`min_score_to_queue: 7`, now on the v2 scale)

With final weights, on the reviewed population (15 pos + 283 hard = 298 rows the user actually acted on):

| t | pos kept | hard queued | F = kept/298 | adds/day (16 × F) |
|---|---|---|---|---|
| 5 | 13/15 | 135/283 | 0.50 | ~8 |
| 6 | 12/15 | 106/283 | 0.40 | ~6 |
| **7** | **11/15** | **90/283** | **0.34** | **~5** |
| 8 | 10/15 | 60/283 | 0.23 | ~4 |
| 9 | 10/15 | 44/283 | 0.18 | ~3 |

Decision: **7 stays**, documented in a dated `search.yaml` comment. Rationale:
- t=6 buys exactly +1 apply recall (GTM Specialist at 6) for ~+16 queue rows/day — the same trade report 06 §5 rejected for v1 ("7→6 buys a band with 0 lifetime applies"), and the 09-12 6→7 recalibration was behaviorally validated. The 301-row bulk-wiped v1-6 class maps to v2 scores ≤6 by construction (adjacent/off family or duties ≤1 ⇒ 2–6), so they stay below.
- These adds/day figures are a **floor** on the v1-queued re-score path; they exclude jobs v1 *skipped* that v2 may now pass (v2's DQ set is narrower: no USD-inference, no posting-format strictness, years only DQ at ≥5). The labeled set can't see that inflow (no labels on v1-skipped jobs). Naive labeled-fraction method (kept/328 × 260) gives ~80/day — an over-estimate ~15× because the labeled set is 91% v1-queued vs ~6% live. True rate expected between the two; the soak decides (§8).

## 7. `scoring.version: 2` flip + facts write path

- Flipped in `search.yaml` with a dated comment citing the 2026-10-06 evidence (AUC 0.519 collapse, zero 9–10s, 4.5× model gap; offline 0.809→0.821).
- Verified the write path: `pipeline.py:283` stores `res["facts"]` into `score_facts` when present; `Scorer.score()` (v2) merges `compute_v2()`'s output — including `facts` and `score_breakdown` — into the result. Confirmed by a new end-to-end test that runs the **real** Scorer with a fake LLM client through the **real** `pipeline.score_jobs` into a tmp DB and asserts `score_facts` parses with `role_family` + `breakdown`.
- Existing rows are untouched (no rescore by design — URL+fingerprint dedupe, one score per posting); the flip affects only newly scored jobs.

## 8. Live-soak checklist (first v2 run = tomorrow 06:30 digest)

1. **Queue adds/day**: expected 5–16/day. If sustained >25/day → raise `min_score_to_queue` to 8; if <6/day for 3+ days → consider 6 (rerun `retune --threshold 6` first).
2. **9–10s exist**: digest/queue should contain v2 9s/10s again (offline says ~10% of positives-class rows). Zero 9–10s after a few days ⇒ extraction quality problem on lightning (facts too conservative), not weights.
3. **score_facts populated**: `SELECT count(*) FROM jobs WHERE score_facts IS NOT NULL AND scored_at > '2026-10-07'` should equal the number scored.
4. **Model-independence spot-check**: `SELECT scorer_model, count(*), avg(fit_score) FROM jobs WHERE score_facts IS NOT NULL GROUP BY 1` — the 4.5× queue-rate gap between models should collapse since only facts vary now; any big per-model score gap = fact-extraction drift per model (that's the thing to watch, not the score).
5. **US/USD postings**: PosiTrace-class jobs (US employer, USD salary, no explicit Canada exclusion) should now score normally — spot-check one in the digest.
6. **Manager-titled fits**: Operations/CS/Project Manager-class fits should reach 7–9; if they flood the queue, revisit (the offline set couldn't validate this).
7. **one_liners**: should read like "RevOps at a fintech SMB, 2–4 yrs, $70–90k, builds CRM automations; con: on-site 3d" — if "Strong fit" boilerplate persists, the model is ignoring the schema instruction (consider a negative example).
8. **Hidden-employer DQ**: aggregator rows should still skip with "agency / hidden employer" — confirm none queue.
9. **Skipped-rate sanity**: v1's narrower DQs (years 3–4 no longer hard-skip in scoring) mean fewer skip=true rows; that's intended, the threshold does the gating.

## 9. New `retune` subcommand (eval harness)

`venv/bin/python scripts/eval_scorer.py retune v2-off [--threshold N]` — re-runs `compute_v2` over a stored results file's facts with the **current** config weights + family tiers. Zero API calls, zero DB access. This is the loop for all future weight tuning (report 06 idea #9's drift check can also use it monthly). Rows without facts pass through untouched.

## 10. Tests (5 added; suite 141 → 146, all green)

- `test_scorer_v2.py::test_manager_title_not_penalized` — manager seniority + people_manager add zero cost vs the identical non-manager facts.
- `test_scorer_v2.py::test_coordinator_families_demoted_to_adjacent` (×2, parametrized) — implementation_onboarding/project_program_coord score exactly one tier (−2) below a target family on identical facts.
- `test_scorer_v2.py::test_near_perfect_fit_reaches_ceiling` — the apply-profile facts (automation_ai_ops, d3, junior, 1yr, startup, 2 signals) still reach ≥9 post-retune.
- `test_scorer_v2.py::test_v2_score_facts_populated_end_to_end` — real Scorer + fake LLM client through real `pipeline.score_jobs` into a tmp DB; asserts `score_facts` lands with `role_family` + `breakdown`, job queues at ≥7.
- `test_eval_metrics.py::test_retune_rows_recomputes_scores` — retune recomputes from facts, passes factless rows through, does not mutate inputs.

## 11. Validation

- `venv/bin/python -m ruff check autojob/` → **All checks passed**
- `venv/bin/python -m pytest -q` → **146 passed** (9.7 s)
- `scripts/eval_scorer.py retune v2-off` → AUC 0.821, numbers as in §5
- Pre-existing lint findings in `scripts/expand_ats_boards.py` and `scripts/test_models.py` were NOT touched (outside the gate `ruff check autojob/` and outside my ownership).

## 12. Files changed (no commits, nothing staged)

- `pipeline/autojob/scorer.py` — family demotions + people_manager default 0 (with dated comments)
- `pipeline/config/search.yaml` — scoring section only: version 2, weight updates, quoted `'off'`, dated threshold-math + flip comments
- `pipeline/prompts/scorer_v2.md` — explicit-US-only location rule; discriminating one_liner spec
- `pipeline/scripts/eval_scorer.py` — `retune_rows()` + `retune` subcommand (+ `--threshold`)
- `pipeline/tests/test_scorer_v2.py`, `pipeline/tests/test_eval_metrics.py` — 5 new tests

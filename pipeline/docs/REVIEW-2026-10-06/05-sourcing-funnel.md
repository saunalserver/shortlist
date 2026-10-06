# Slice 5 — Sourcing Funnel Review (2026-10-06)

Repo `pipeline` @ `877686c` (v2.4.0). All numbers from read-only queries on `pipeline/data/autojob.db` (`mode=ro`) and code at HEAD. Lifetime funnel: **26,398 jobs fetched → 17,169 prefiltered → 8,263 skipped → 961 ever-queued (829 queued + 121 expired + 16 docs) → 18 applied (0.07% end-to-end)**.

---

## 1. Per-source funnel table (lifetime)

`ever-queued` = queued + expired + docs_generated (jobs that reached the review queue at some point). `LLM/queued` = scored calls per ever-queued job (cost proxy).

| source | raw fetch¹ | new (dedup'd) | uniq % | prefiltered | skipped | scored | ever-queued | queued % | applied | LLM/queued | avg score |
|---|---|---|---|---|---|---|---|---|---|---|---|
| boards (LinkedIn+Indeed) | 66,726 | 12,091 | 18.1 | 8,053 | 3,629 | 4,038 | 409 | 3.4 | 6 | 9.9 | 3.12 |
| serper | 7,767 | 4,123 | **53.1** | 2,428 | 1,555 | 1,695 | 140 | 3.4 | 4 | 12.1 | 3.01 |
| adzuna | 51,719 | 3,816 | 7.4 | 2,657 | 1,053 | 1,159 | 106 | 2.8 | 2 | 10.9 | 3.00 |
| himalayas | 46,616 | 1,657 | 3.6 | 916 | 645 | 741 | 96 | 5.8 | 2 | 7.7 | 3.55 |
| ats_companies | 60,977 | 1,374 | 2.3 | 1,025 | 251 | 349 | 98 | **7.1** | 2 | **3.6** | 3.95 |
| workday | 52,332 | 1,292 | 2.5 | 774 | 484 | 518 | 34 | 2.6 | 0 | 15.2 | 2.72 |
| jooble | 18,042 | 875 | 4.8 | 580 | 260 | 295 | 35 | 4.0 | 0 | 8.4 | 3.16 |
| amazon | 18,099 | 381 | 2.1 | 317 | 60 | 64 | 4 | **1.05** | 0 | 16.0 | 2.17 |
| eluta | 6,020 | 178 | 3.0 | 75 | 76 | 103 | 27 | **15.2** | 0 | 3.8 | **4.38** |
| wttj | 371 | 25 | 6.7 | 5 | 16 | 20 | 4 | 16.0 | **1** | 5.0 | 4.10 |
| weworkremotely | 2,150 | 93 | 4.3 | 54 | 35 | 39 | 4 | 4.3 | 0 | 9.8 | 3.08 |
| remoterocketship | 694 | 32 | 4.6 | 10 | 18 | 22 | 4 | 12.5 | 0 | 5.5 | 3.95 |
| hn | 2,971 | 91 | 3.1 | 31 | 58 | 60 | 2 | 2.2 | 0 | 30.0 | 2.32 |
| yc (disabled 09-07) | 126 | 12 | 9.5 | 10 | 1 | 2 | 1 | 8.3 | 1 | 2.0 | 5.50 |
| successfactors / gcjobs / workable_search / bcps / getro / workingnomads (new 09-28) | 1,728 | 130 | 7.5 | 49 | 59 | 65 | 1 | 0.8 | 0 | 65.0 | ~2.2 |

¹ `SUM(fetched)` from `source_runs` (pre-dedupe, all runs incl. disabled sources' active periods).

**Reading**
- **Volume engines**: boards + serper + adzuna = 76% of all new jobs and 68% of ever-queued. Serper is the efficiency standout on fetch: 53% unique (everything else ≤18%) — it searches ATS domains directly so almost nothing is a repeat.
- **Quality per LLM call**: `ats_companies` is the best source nobody talks about — 7.1% queued at only 3.6 LLM calls per queued job (3× better than boards) and the second-highest avg score. `eluta` has the highest yield % (15.2%) and avg score (4.4) but tiny volume and snippet-only scoring.
- **Hidden gems**: `wttj` (1 apply from 25 jobs — best applied/new ratio of any live source), `remoterocketship` (12.5% queued, 5.5 LLM/queued). Both added 09-28; too small to be load-bearing yet but the signal is right.
- **Dead weight**: `amazon` — 18k raw fetches for 381 new, 4 ever-queued (1.05%), 0 applied, 16 LLM/queued. `workday` — 15.2 LLM/queued, 2.6% queued, **0 applied from 1,292 jobs** (big-bank tenants mostly feed Toronto roles that then die in prefilter). `hn` — 30 LLM/queued.
- **The 09-28 expansion (9 new sources) has produced 130 new jobs and exactly 1 queued-relevant outcome (1 apply via wttj) in 8 days** — 0 queued from successfactors(46), gcjobs(32), workable_search(6), bcps(6), getro(4); 4 from remoterocketship, 4 from wttj, 1 from workingnomads. Early, but at this rate the expansion added queue volume it didn't add quality.

---

## 2. prefilter_reason distribution and false negatives

Distribution of the 17,169 prefiltered: **title 13,975 (81.4%) · location 2,037 (11.9%) · posted-too-old 598 (3.5%) · employment-type 559 (3.3%)**.

Top title kills: `senior` 3,237 · `director` 824 · `lead` 769 · `sr` 430 · `representative` 429 · `executive` 332 · `supervisor` 277 · `technician` 247 · `warehouse` 222 · `quality` 180 · `operator` 175. Top location kills: `toronto` 652 · `United States` 310 · `montréal` 230 · `calgary` 160 · `edmonton` 127 · `mississauga` 123.

**False-negative sampling** (random samples ≥ the smaller of 50/all, per bucket; rules in `pipeline/autojob/prefilter.py:133-155`, words in `config/search.yaml:66-360`):

| bucket | sampled | verdict | est. FN |
|---|---|---|---|
| `title: senior` | 60 | Correct seniority policy kill; only "Senior Program Assistant @ UBC" borderline | ~3% |
| `title: representative` | 115 | CSR/sales noise; ~5 ops-adjacent ("Operations Support Representative 3") | ~4% |
| `title: supervisor` | 60 | Ops-supervisor roles but seniority-inappropriate for early-career profile | ~5% |
| `title: quality` | 57 | Mostly manufacturing/software QA; ~6 borderline ("Quality Process Improvement Analyst") | ~10% |
| `title: clerk` | 24 | Admin noise; "IT Procurement Clerk" borderline | ~5% |
| `title: operator` | 42 | Equipment/machine operators | ~0% |
| `title: planner` | **all 58** | **~16 squarely in the supply-chain target family**: "Supply Planner"×2, "Demand Planner", "Supply Chain Analyst, Replenishment Planner", "REXEL Inventory Planner"×2, "Production Planner/Coordinator (Maple Ridge)", "Sales Operations/Demand Planner", "Order Management & WorkForce Planner", "Logistics Coordinator – Load Planner"×2, "Deployment Planner and Logistics Coordinator"… | **~28%** |
| `title: buyer` | **all 36** | **~13 procurement-family**: "Buyer, Supply Chain"×2, "Supply Chain Buyer II", "Purchasing Analyst/Buyer", "Procurement Buyer"×2, "Junior Buyer"×2, "Buyer/Procurement Specialist", "Associate Procurement Specialist–Buyer", "IT Procurement Specialist (Buyer III)" | **~36%** |
| `title: scheduler` | all 20 | ~4 borderline ("Logistics Coordinator (Scheduler)") | ~20% |
| `employment type:*` | 25 | Contract/temp policy kill; ~2 source-mislabeled permanents ("Business Analyst [Contractor]") | ~8% |
| `posted:*` | — | Stale-on-arrival by design | ~0% |

**Title-rule estimated FN rate ≈ 1.5–2% of prefiltered (~260–340 jobs over 33 days)** — concentrated exactly in the supply-chain family the owner added queries for on 09-06 (`search.yaml:50-54`). `planner`+`buyer`+`scheduler` = 114 kills, ~33 clear FNs. The generic noise words are working as intended.

### 🐛 Bug A (verified live at HEAD): `"Remote, CA"` is parsed as California

`prefilter.py:113-114`: the US-state regex `,\s*([a-z]{2})\s*$` matches the trailing `ca`; `"ca"` is not in `_CA_PROVINCES` (`prefilter.py:27`) and "Remote, CA" contains no `CANADA_MARKERS` → every such job returns `location: United States`. Reproduced on HEAD:

```
location_reason("Remote, CA", cfg, remote=1)  ->  'location: United States'
```

Boards' Canada `remote_only` pass writes exactly `location='Remote, CA'` (`search.yaml:563-566`). **All 281 `Remote, CA` rows ever fetched are prefiltered; 0 have ever been scored.** 106 died directly on this bug (the rest on title rules first). The pass that config describes as "keeps only remote-flagged rows" delivers **zero** jobs to the LLM. Victims sampled: "Revenue Operations Manager @ Mimecast", "Adoption Specialist @ Solventum", "Digital Product Enablement Specialist @ Element Fleet", "Product Owner, Intermediate – Remote Canada @ Smile CDS". At boards' baseline (~33% pass prefilter, ~10% of scored queue) that's ~10+ lost queued-equivalents in 5 weeks — small in count, but these are remote-Canada jobs, the single best policy fit, and the pass is otherwise pure waste (40 queries × 35 results per run).

### 🐛 Bug B (verified live at HEAD): the source `remote` flag is ignored

`prefilter.py:95`: `says_remote = remote is True or …` — but `pipeline.py` feeds prefilter dicts straight from SQLite (`D.get_jobs`, `db.py:348-356`), where `remote` is **int 1**, not `bool True`, so `is True` is always False. The docstring (`prefilter.py:7-9`) says the flag should count as remote wording; it never does. Reproduced:

```
location_reason("Toronto, ON", cfg, remote=1)    ->  'location: toronto'   (bug)
location_reason("Toronto, ON", cfg, remote=True) ->  None                 (intended)
```

**504 jobs with `remote=1` were killed by deny-city rule 1** (toronto 191, montréal 59, calgary 52, edmonton 39, mississauga 30, ottawa 25…). A 50-row sample showed ~20% clearly target-family remote roles ("Business Systems Analyst @ CIBC", "Billing Operations Associate @ Instacart", "Bilingual Customer Experience Coordinator (EN/FR) – Remote @ Phoenix", "Customer Onboarding/Activation Specialist @ Condo Control Central"). Est. +15–25 lost queued-equivalents over 5 weeks.

**Location-bucket FN rate including bugs: ~30% of the 2,037 location kills (≈600 jobs) were killed contrary to the documented policy**; ~15–20% of those look genuinely relevant. Overall prefilter FN ≈ 2.5–3% of 17,169 (~430–510 jobs, ~13–15/day) — the funnel is high-precision, but its misses cluster in remote-Canada and supply-chain, i.e. the newest, most-wanted supply.

---

## 3. skipped=8,263 · expired=121 · queued=829

- **skipped = 8,263** is produced at `pipeline.py:267-271`: any scored job with `res["skip"]` (LLM's own disqualifier: `1.A seniority` 94, `1.C role-type` 82, `1.B location` 69) or `fit_score < min_score_to_queue`. Score histogram: 4,472@2, 1,587@3, 679@4, 631@5, 346@6, **3@7 and 1@8** (LLM-skip flag overrides a passing score — rare, by design). All 8,263 are v1-scorer rows (`score_facts IS NULL`). Nothing good is hiding here: at 7+ the bucket contains 4 rows total, and 18 lifetime applies scored 7×4, 8×11, 9×2, 10×1 — the threshold is empirically right.
- **expired = 121: every single one was never reviewed** (`user_action IS NULL` for all 121; 98 scored 7, 4 scored 8, 19 scored 6). `expire.py` retires on age/link-death regardless of review state. That is **102 score-7+ jobs produced, surfaced in digests Victor didn't get to, and silently destroyed** — the largest measured loss of good jobs in the system, bigger than all prefilter FNs combined.
- **queued = 829 backlog**: 316 legacy score-6 (all reviewed/dismissed in the 09-12 recalibration clear-out), **337 score-7 with 230 unreviewed**, 176 score-8/9 with 6 unreviewed → live backlog ≈ **236 unreviewed 7+ jobs**, aged 2026-09-03→10-06. Digest shows only the top **15** of each run's new shortlist (`notify.py:16,74`), so the backlog is invisible day-to-day. Since the 09-28 expansion the funnel queues **16.1 jobs/day** (vs 6.6/day the week before) while Victor's lifetime apply rate is **0.55/day** (review bursts: 71 dismissed + 8 applied on 10-05). The funnel now produces a queue ~30× faster than it is consumed; the 121-expired-unreviewed number will repeat — the next cohort of 09-03-fetched queue rows hits `fetched_max_days=45` around **2026-10-18**.

---

## 4. Dedupe across sources

- `seen_urls` = 36,345 vs 26,398 distinct URLs in `jobs` → **9,947 dup-URL fetches (27%) ignored** at insert (`db.py:314`). `jobs.url` is UNIQUE — 0 URL collisions stored.
- Fingerprint dedupe (`normalize.py:108`: normalized title + 2-word company key) fires at insert (`db.py:320`), first-writer-wins → **0 fingerprints exist on 2+ sources in `jobs`**; cross-source duplicates cost a re-fetch, never a re-score. Double LLM spend via fingerprint: none.
- Canonical-URL misses: same posting with slightly different *titles* escapes fingerprinting. Measured as same company + first-25-chars-of-title scored in 2 different sources: **47 pairs** (~2% of scored, ~94 wasted LLM calls) — boards↔serper 16, adzuna↔serper 8, himalayas↔serper 5, jooble↔serper 5. Negligible; no action needed.
- The real dedupe tax is **re-fetching unchanged boards**: ats_companies 2.3%, workday 2.5%, himalayas 3.6% unique per run — 97%+ of each run's fetch is already-known listings (cheap requests, but it's why fetched/day is ~11k for ~700 new).

---

## 5. Volume + quota reality since the 09-28 expansion

| metric | week before 09-28 | 09-29 → 10-06 | Δ |
|---|---|---|---|
| fetched / day | ~9,200 | ~11,100 | +21% |
| new jobs / day | 513 | 702 | +37% |
| scored (LLM) / day | ~200 | ~260 | +30% |
| queued / day | 6.6 | **16.1** | **+144%** |
| applied | — | 10 (8 on 10-05) | bursty |

- **Serper**: 48 credits/run × 2 runs = 96/day planned (`search.yaml:533`). `meta.serper_credits_used` = **817** — undercounts real burn (counter only adds the API-reported `credits` field per call, `serper.py:113,126-139`; theoretical burn since the 09-07 raise is ~2.8k). Key is alive and it's the most productive source per request: 141–228 rows, 46–81 new per run (33% uniq).
- **Jooble**: 30 requests/run × 2 runs = **60/day against a 500-request LIFETIME key** (`search.yaml:547-551`, `scripts/jooble_key.sh`) — a key lasts ~8 days at this rate; either keys are being swapped quietly or Jooble isn't enforcing. Marginal value is now poor: 277–290 rows/run → **1–8 new per run (~2%)**, lifetime 875 new → 35 queued (4.0%), **0 applied**, last new-queued 09-15.
- **LLM quota vs paid-first** (v2.4.0, `llm.py` probes `GET /api/v1/key`): scoring runs paid-first (~$0.0003/call) at ~250–330 calls/day typical (521 on 09-29's 4 runs) → **~$0.08–0.16/day**, i.e. the ~$9.8 credit lasts ~2–3 months. Free bucket (1,000/day, reserve 250) is now backstop only. Consequence: **every prefilter loosening costs ~$0.0003 × extra-scored** — the planner/buyer carve-out below would cost roughly $0.01/day. Money is not the constraint; review attention is.

---

## 6. Improvement ideas (impact vs effort, ranked)

1. **Fix prefilter Bug A ("Remote, CA" → US)** — `prefilter.py:114`: accept `ca` as Canada when the string names no US city/state context, or add `"remote, ca"`-style handling / a `CANADA_MARKERS` entry for `, ca$`. *Impact: high for effort — un-bricks the boards remote-Canada pass (281 jobs, 0 ever scored); ~10–15 queued-equivalents/5wk of best-policy-fit supply. Effort: ~2 lines + optional one-off requeue (`UPDATE jobs SET status='new' WHERE location='Remote, CA' AND prefilter_reason='location: United States'` — needs a write, not done here).*
2. **Fix prefilter Bug B (`remote is True` → `bool(remote)`)** — `prefilter.py:95`. *Impact: ~504 mis-killed remote jobs/5wk, est. +15–25 queued-equivalents. Effort: 1 line.*
3. **Stop good jobs dying unreviewed** — the funnel's #1 real loss (121 expired unseen, 236 unreviewed backlog, 16.1 queued/day vs 0.55 applies/day). Options in impact order: (a) auto-expire *unreviewed* queue entries at ~14 days with a digest "expiring soon" nudge instead of silent death; (b) raise `min_score_to_queue` to 8 and let 7s go to a "maybe" list (4 lifetime applies at 7 vs 14 at 8+); (c) digest already caps at 15 — add a weekly backlog rollup line. *Impact: highest in the whole system. Effort: small (expire.py + notify.py).*
4. **Supply-chain title carve-out** — allow-phrase `planner|buyer|scheduler` when the title also contains supply/demand/inventory/procurement/logistics/replenishment/load (mirror of the existing `title_allow_phrases` mechanism, `search.yaml:60-65`). *Impact: ~33 clear FNs recovered per 5 wks, all in the 09-06 target family; ~$0.01/day LLM. Effort: ~10 yaml lines.*
5. **Prune dead-weight sources** — disable `amazon` (1.05% queued, 16 LLM/queued, 0 applied, 18k fetches/run-day) or cut `result_limit`; cut `jooble` to one pass/day or disable until supply refreshes (60 req/day for ~3 new). *Impact: −60–70 LLM calls/day of worst-yield scoring, saves the 500-lifetime key. Effort: config only.*
6. **Feed the efficient sources** — `ats_companies` (7.1% queued, 3.6 LLM/queued) has 823 verified boards in `ats_boards` + 10,195 cached companies (`company_ats_cache`) and uses ~120 hand-listed slugs; widen `use_discovered_boards` coverage. Keep/raise `eluta`, `wttj`, `remoterocketship` (12–16% yield). *Impact: medium, compounding. Effort: medium.*
7. **Policy decision needed: US-remote** — the task brief says US remote is acceptable, but `deny_us: true` drops US-remote even when flagged remote (`prefilter.py:105-116`; **307 US-remote jobs killed**). If genuinely in-policy, a US `remote_only` boards/serper pass is the largest untapped pool; if not, no change. *Impact: potentially large. Effort: 1 config flag + a pass — but only the owner can decide.*
8. Cosmetic: `meta.serper_credits_used` undercounts (817 tracked vs ~2.8k theoretical); fix the counter or read the dashboard from serper.dev.

**Bottom line**: the funnel's precision is good (seniority/noise title rules: ~96% correct; threshold 7 validated by apply data), but two verified one-line prefilter bugs are throwing away the exact remote-Canada supply the 09-28 policy asked for, the supply-chain title words eat their own queries, and — bigger than all of it — the queue now produces 16 jobs/day against a 0.55/day apply rate, so good jobs expire unreviewed faster than Victor can see them. Fix the two prefilter lines, then fix the review loop before adding any more sourcing.
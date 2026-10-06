# Agent A — Pipeline fixes (Phase 0 + digest), implementation log

Repo `/home/saunalserver/projects/shortlist`, pipeline @ 877686c. All 19 items done. **No commits made.**
Production DBs never written: all queries were `mode=ro`; the only write test was `D.init_db()` on a `/tmp` **copy** of `autojob.db` (deleted after).

Final checks: `venv/bin/python -m ruff check autojob/` → **All checks passed** · `venv/bin/python -m pytest -q` → **140 passed** (was 125 passed / 1 failed). `ruff check autojob tests` also clean.

---

## 1. Prefilter Bug A — "Remote, CA" parsed as California
- `pipeline/autojob/prefilter.py:95-99`: `canada = canada or bool(re.fullmatch(r"remote[\s,\u2013-]+ca", loc))` — a location that is *essentially* "remote" + province-style CA is Canada-remote and passes (rule 2 skipped; rules 1/3 already can't kill it). Genuine US cities keep dying in rule 2 (state regex untouched).
- Test: `tests/test_prefilter.py::test_remote_ca_is_remote_canada_not_california` — `("Remote, CA", remote=1)` → None, `("Remote - CA")` → None, `("San Francisco, CA")` → `location: san francisco (US)`, `("Los Angeles, CA")` → `location: los angeles (US)`, `("Fresno, CA")` → `location: United States`.
- Read-only validation on production data: of the 281 `Remote, CA` rows, **123 now pass all prefilter rules** (the rest still die on `senior`×32, `director`×13, `lead`×11… — correct kills). Requeue of those rows is an owner decision (plan Part 3 item 2), not done here.

## 2. Prefilter Bug B — `remote is True` vs SQLite int 1
- `pipeline/autojob/prefilter.py:101`: `says_remote = bool(remote) or …` — the source remote flag now counts as remote wording.
- Test: `tests/test_prefilter.py::test_source_remote_flag_counts_as_remote_wording` — `location_reason("Toronto, ON", cfg, remote=1)` → None (no longer dies on the toronto deny rule); `remote=0` still → `location: toronto`.

## 3. Supply-chain title carve-out
- `pipeline/autojob/prefilter.py:152-157`: when the title contains a `title_sc_markers` word, the `title_sc_words` (planner/buyer/scheduler) are removed from the exclusion list — **only those words**; senior/director/contract phrases still kill. Mirrors `title_allow_phrases` config style.
- `pipeline/config/search.yaml:159-164`: `title_sc_words: [planner, buyer, scheduler]`, `title_sc_markers: [supply, demand, inventory, procurement, logistics, replenishment, load]` with dated comment.
- Test: `tests/test_prefilter.py::test_supply_chain_title_carve_out` — "Supply Chain Buyer II", "Demand Planner", "Logistics Coordinator (Scheduler)" pass; "Media Buyer", "Appointment Scheduler", "Production Planner" still die on title; "Senior Demand Planner" → `title: senior`; "Supply Chain Buyer (Contract)" → `title: (contract`.
- Read-only validation: of the 115 historical planner/buyer/scheduler title kills, 20 now pass — all squarely supply-chain ("Supply Planner", "Buyer, Supply Chain", "REXEL National Inventory Planner", "Supply Chain Buyer II", "Associate Procurement Specialist - Buyer"…).

## 4. Company blocklist (plan item 18)
- `pipeline/autojob/db.py:401-413`: `company_dismissal_counts(conn)` — one query per run (`GROUP BY company`, deliberate = dismissed AND fit_score >= 7), companies keyed with `normalize.company_key` exactly like fingerprints. (First draft was missing `GROUP BY` — caught by the read-only production simulation, fixed, test hardened.)
- `pipeline/autojob/prefilter.py:138-146`: `prefilter_reason(job, cfg, company_blocklist)` → `"company_blocklist"`; `pipeline/autojob/pipeline.py:421-427` computes the set once in `run()` and passes it into the prefilter step.
- `pipeline/config/search.yaml:502-506`: `prefilter.company_blocklist: {enabled: true, min_dismissals: 2}` with dated comment.
- Tests: `tests/test_db.py::test_company_dismissal_counts_exclude_bulk_wipe` (tmp DB; score-6 bulk-wipe row excluded, same-company spelling variants merge, second offender counted); `tests/test_prefilter.py::test_company_blocklist_skips_repeat_offenders`; `tests/test_pipeline_steps.py::test_pipeline_prefilter_applies_company_blocklist` (wiring).
- Read-only validation: 28 companies blocked on real data (sailor health ×6, jobber ×4, university-of ×4, best buy/brex/ewor/roylo ×3…).

## 5. Digest window fix (report 03 Bug 3)
- `pipeline/autojob/db.py:395`: `queued_since` gains `AND user_action IS NULL` (no re-shows of acted jobs).
- `pipeline/autojob/pipeline.py:456-459`: window bound at previous done run's **`finished_at`** (was `started_at`) — no double-listing across consecutive digests; carry-over from aborted/killed runs still included.
- Test: `tests/test_digest.py::test_queued_since_skips_acted_jobs`.

## 6. Digest demotions (report 06 items 1-2)
- `pipeline/autojob/notify.py:66-97` (`digest_jobs`): drops candidates with `scored_at` older than 14 days and `low_confidence=1`. Dashboard visibility unchanged — this only affects digest build.
- Test: `tests/test_digest.py::test_digest_demotes_stale_and_low_confidence`.

## 7. Composite digest ranking (plan item 19)
- `pipeline/autojob/notify.py:66-97`: `rank = fit_score + source_prior + freshness − low_conf_penalty − company_dismiss_count`, sorted in Python (SQL untouched beyond item 5); top-15 cap kept. Freshness: full `freshness_bonus` at ≤ 3 days since scored_at, linear decay to 0 at 14 days.
- `pipeline/config/search.yaml:125-146`: new `digest_ranking:` section — `freshness_bonus: 1.0`, `low_confidence_penalty: 1.0`, static `source_priors` rounded to 0.25 steps with the raw rates and a monthly-recompute comment + query.
- Priors computed NOW from production DB (read-only; applied/(applied + deliberate-dismissed@7+) per source): serper 4/36=11.1%→1.0 · ats_companies 2/20=10.0%→1.0 · wttj 1/4=25%→0.75 (tiny sample) · adzuna 2/31=6.5%→0.5 · boards 6/125=4.8%→0.5 · himalayas 2/48=4.2%→0.25 · 0-apply sources (jooble 0/26, workday 0/24, eluta 0/15, …) → 0.0 default.
- Tests: `tests/test_digest.py::test_digest_ranking_composes_score_prior_freshness_and_company_history` (checks exact ranks 9.91/9.5/9.0/8.0 incl. decayed freshness and −2 company history).
- Note: the `low_confidence_penalty` term is unreachable while item 6 excludes low-conf rows from the digest — kept because it is part of the specified formula and becomes live if the demotion is ever relaxed.

## 8. Expiring-soon digest line (plan item 12)
- `pipeline/autojob/pipeline.py:461-463`: count = `len(D.stale_by_age(conn, posted_max_days-3, fetched_max_days-3))` — reuse of the age rule at limits−3 days over active (queued, `user_action IS NULL`) jobs; expire() already ran this run, so survivors inside 3 days of either limit are exactly the flagged set.
- `pipeline/autojob/notify.py:125-127`: line after the job list: "⏳ N pending jobs retire within 3 days — review now."
- Test: `tests/test_digest.py::test_digest_carries_expiring_soon_line`. Read-only validation: 32 on today's real queue.

## 9. Commit per scrape (report 03 Bug 2)
- `pipeline/autojob/pipeline.py:211-212`: `conn.commit()` moved inside the scrape loop (per scrape, matching expire.py's per-link commit); the old single commit after the loop removed. No ~15-min write transaction; dashboard Apply/Dismiss no longer risks SQLITE_BUSY during scraping.
- No dedicated test (one-line commit-placement change; covered by ruff + existing suite).

## 10. expire() clock injection (report 03 Bug 1)
- `pipeline/autojob/expire.py:59-63`: `today: datetime | None = None` param passed through to `D.stale_by_age`.
- `tests/test_expiry.py::test_age_rules` now pins `clock = datetime(2026, 9, 2, tzinfo=UTC)` and injects it into both `stale_by_age` and `expire` — no wall-clock dependence. **Suite fully green** (the previously red test).

## 11. CI
- New `.github/workflows/ci.yml`: on push + pull_request → checkout, Python 3.12 (matches venv 3.12.3), `pip install -r pipeline/requirements.txt` (pytest+ruff already in it), `ruff check pipeline/autojob/`, `pytest -q` in `pipeline/`. No secrets.

## 12. LLM circuit breaker (report 03 Bug 5)
- `pipeline/autojob/pipeline.py:29-30` (`LLM_FAILURE_STOP = 10`) and `269-277`: consecutive-failure counter in `score_jobs` (reset on any success); at 10 → `stop = True` (remaining jobs stay `new`), reason recorded via `RunSummary.notes` → `runs.notes` (`as_row` now emits notes when set, pipeline.py:63-72).
- Test: `tests/test_score_parallel.py::test_llm_circuit_breaker_stops_the_run` (stops at 10-12 scored of 30, rest stay `new`, notes lands in the runs row).

## 13. Zombie run sweep (report 03 Bug 6)
- `pipeline/autojob/db.py:500-510`: `sweep_orphaned_runs(conn, keep_run_id)` — guarded UPDATE, `status='error'`, `finished_at` backfilled, note appended. Called at run start (`pipeline.py:391-393`) — safe because the run lock guarantees no other live run. Production rows #22/#53 will be swept by the next run; **DB not touched manually**.
- Test: `tests/test_db.py::test_orphaned_runs_are_swept` (current run untouched, idempotent).

## 14. claim_next_command atomicity (report 03 Bug 7)
- `pipeline/autojob/db.py:559-569`: guarded `UPDATE … WHERE id = ? AND status = 'pending'`, returns `None` on `rowcount == 0`.
- Test: covered by `tests/test_db.py::test_fresh_db_and_commands` (second claim returns None) — the concurrent-claim rowcount path is exercised by the same no-double-claim assertion; no true concurrency test added (single poller today).

## 15. Worker abort-flag guard (report 03 Bug 4)
- `pipeline/autojob/pipeline.py:320-323`: `_check_abort` only when `summary is not None` (run context) — a standalone `docs` command (worker subprocess / CLI) no longer consumes the run's abort flag.
- Test: `tests/test_pipeline_steps.py::test_docs_command_does_not_consume_the_run_abort_flag` (flag untouched without summary, honoured with).

## 16. Zero-fetch surfacing (report 03 Bug 8)
- `pipeline/autojob/pipeline.py:155-158`: when a source returns 0 rows without raising, `source_runs.error` gets `"warning: 0 rows fetched — source dead or blocked?"` (flows through the existing `record_source_run` path).
- Test: `tests/test_pipeline_steps.py::test_fetch_all_flags_zero_row_sources`.

## 17. Schema: dismiss_reason
- `pipeline/autojob/db.py:123` (schema), `:243-245` (idempotent `ALTER TABLE … ADD COLUMN dismiss_reason TEXT` in `init_db`), `:48` (`JOB_COLUMNS`, so `update_job` can write it). Additive, NULL default — dashboard agent writes it in parallel.
- Tests: `tests/test_db.py::test_fresh_db_and_commands` (column present); migration verified on a /tmp **copy** of the real 109 MB DB (column added, `user_version` intact, second init no-op).

## 18. Sources prune
- `pipeline/config/search.yaml`: `jooble.enabled: false` (line ~738; 60 req/day burns a 500-lifetime key in ~1 wk for ~2% new, 0 applied, last queue contribution 09-15) and `amazon.enabled: false` (line ~812; 18k fetches → 4 queued (1.05%) → 0 applied, 16 LLM/queued), both with dated comments.

## 19. Final verification
- `cd pipeline && venv/bin/python -m ruff check autojob/` → **All checks passed!**
- `cd pipeline && venv/bin/python -m pytest -q` → **140 passed in 9.65s** (14 new tests; the previously failing `test_age_rules` green).

---

## Deliberately skipped / not done (owner decisions, per plan)
- **Requeue of the 281 `Remote, CA` + remote-flag victims** (plan Part 3 item 2) — requires a production write; orchestrator/owner call. 123 of the 281 would pass the fixed prefilter today.
- **US-remote policy** (deny_us) — Part 3 item 1, owner decision, untouched.
- Retry cap for `error` jobs, runs.scored conflating errors — report-03 nits, out of scope.
- `low_confidence_penalty` is currently unreachable in ranking (low-conf rows are digest-excluded) — kept for formula fidelity, documented above.
- No commit made, per hard constraint. `dashboard/*` modifications visible in `git status` belong to the parallel dashboard agent, not this task.

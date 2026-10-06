# Slice 3 — Pipeline code bug hunt (autojob Python)

**Scope:** `git show 877686c` traced in full; `llm.py`, `scorer.py`, `pipeline.py`, `cli.py`, `db.py`, `prefilter.py`, `expire.py`, `scraper.py`, `notify.py`, `normalize.py`, `worker.py`, `settings.py`, `sources/*` read end-to-end; read-only SQLite queries against `pipeline/data/autojob.db`; log tail of `data/autojob.log`; systemd units; `ruff` + `pytest` run (tests are `tmp_path`-isolated — production DB untouched). Repo state: clean tree at `877686c`.

**Headline:** the 2.4.0 paid-first chain is **solid** — no quota miscount, no money-burn bug, empty completions gone from live evidence. But the test suite is **red right now** (wall-clock time-bomb in `expire()`), the scrape phase holds a SQLite write transaction for up to ~15 minutes (dashboard dismiss/applied clicks can fail during it), and the digest re-lists jobs you already acted on. 8 findings, ranked at the end.

---

## 1. The 2.4.0 paid-first scoring chain (commit 877686c)

### 1.1 Free-quota probe — correct, no miscount, no early jump to paid

Mechanics (`llm.py:167-211`): before the first call and every `quota_recheck_every` (100) calls, `GET /api/v1/key` reads the **server-side** remaining count (`free_model_daily_requests.remaining`) — there is no local counting to drift. The check-and-set of `_free_probe_done` / `_free_probed_calls` happens under `self._lock` (llm.py:184-189), so with 4 scoring workers exactly one thread probes per window — no thundering herd, no double probe. A failed probe returns `None` and never breaks a run (llm.py:178-181); `quota_recheck_every: 0` disables it entirely (tested in `test_llm_parsing.py`). Benching sets `depleted=True` on `:free` + `openrouter/free` models only; if *nothing* non-free remains it raises `LLMBudgetExceeded`, which `Scorer.score` re-raises so remaining jobs stay `new` for the next run (`scorer.py:50-52`, handler at `pipeline.py:256-261`).

Live evidence it behaves as designed:
- `data/autojob.log` (run 80, 2026-10-06): `OpenRouter free bucket: 1000 remaining (reserve 250, recheck every 100 calls)` at 07:40:06 and 07:43:43 — probe at call 0 and call 100 of a 106-call run. Cadence exact.
- Runs 67-80 (all post-2.4.0): `scored == llm_calls` in 13 of 14 runs (run 71: 180 vs 182) and `errors = 0` in every one — one paid call per job, zero retries, zero fallbacks.

**The money-burn question, answered:** the probe cannot "jump to paid early" — paid is *already first* in the chain. The probe only benches free backstops. The actual economics: ~106-192 calls/run × ~$0.0003 ≈ **$0.03-0.06/run (~$0.06-0.12/day)**, while the 1,000/day free bucket expires **unused every day** (log shows 1000 remaining at every probe). That is the documented owner tradeoff (search.yaml:87-97, "2026-09-29 PAID-FIRST (user call)"), not a bug — but the probe now makes a smarter policy possible for free (see improvement ideas).

Minor accounting nits (all harmless): `self.calls` counts paid+free completions, so probe cadence is driven by paid calls in this chain; exception attempts don't increment `calls` (probe slightly slower under errors); benching isn't atomic against an in-flight free call (≤4 extra free calls slip through).

### 1.2 Model fallback + cooldown logic — sound

`_try_model` (llm.py:233-332): 2 attempts per model; daily-quota 429 → drop for run; provider-429 → 90 s cooldown; per-minute 429 → 15 s retry then 60 s cooldown; `400/401/402/403/404/422` → immediate drop (402 logged as "out of credit — top up OpenRouter"); overload/timeout → 3 s retry then 90 s cooldown; non-JSON validated in-place (llm.py:268) so a JSON-broken model falls through without burning the job. The all-cooling wait loop (llm.py:222-230) waits once for the soonest cooldown, capped at 120 s, then gives up with `LLMAllModelsFailed` — no unbounded stall. Per-model `failures` resets on success; 6 consecutive hard errors drops a model. Pacing: per-model `rpm` + the 3 s account floor now applies **only** to `_is_free()` models (llm.py:236-238) — correct, paid variants have no platform cap.

One real gap: nothing stops the *run* when the provider is hard-down — see Bug 5.

### 1.3 Empty completions — known issue, fixed in practice

Code path (llm.py:256-266): empty completion → no same-model retry, next model takes the call immediately, error streak incremented, model dropped after 6. Combined with `reasoning: "off"` + `max_tokens: 2000` on the free backstops (search.yaml:101-105), live evidence shows the issue is gone: **0** `empty completion` warnings in the last 200 KB of `data/autojob.log`, and `errors=0` across runs 67-80. Historical scale of the problem (search.yaml:82): 12% empty rate on ultra-with-default-reasoning, 166/1,426 calls since 09-21 — that config is gone.

### 1.4 Retry storms — bounded

Worst case per call: 2 attempts × 7 models with 3-15 s sleeps + one ≤120 s all-cooling wait. Per-minute 429s cool in 60 s; daily-quota drops immediately. The account pacer serializes free calls at 20/min. The systemd drop-in (`~/.config/systemd/user/autojob.service.d/`, `TimeoutStartSec=8h`) is the final backstop — a fully wedged run dies at 8 h via SIGTERM, which `_install_sigterm_abort` (pipeline.py:340-352) converts to a graceful abort. 8 h < the 11 h gap between the 06:30/17:30 America/Vancouver timer fires, so the next run is never locked out.

### 1.5 "Marked scored when it was not"

`summary.scored += 1` (pipeline.py:253) fires for error results too — the runs table's `scored` column conflates successes and errors (currently moot: errors=0 everywhere). Error jobs get `status='error'` and are **retried every run with no cap** (carry-over, pipeline.py:385-388) — a poison job would burn ~1 call/run forever. Small, but a retry counter would end it.

---

## 2. End-to-end trace of one run (`pipeline.run`, run #80 as the example)

`expire → fetch (19 sources) → insert/dedupe → prefilter → scrape → score → digest`, 13:39:33→14:44:10 UTC, 65 min.

- **Expire first** (pipeline.py:377-381): retires `queued`/`docs_generated` **with `user_action IS NULL` only** (`db.active_jobs`, db.py:370-373) — acted-on jobs are never expired (test asserts this). Run 80: 5 expired. Rows are never deleted; status flips to `expired` with the reason in `skip_reason` — the "review backlog loss" is by design (search.yaml expiry comment), bounded at 30 d posted / 45 d seen, and recoverable by hand. See Bug 1 for the clock-injection gap in `expire()`.
- **Fetch**: per-source try/except (pipeline.py:124-142) — a raising source logs an error into `source_runs.error` and the run continues. Since 2026-10-01: 19 sources × 12 runs, **0 errors recorded**.
- **Dedupe**: canonical URL (tracking params stripped, LinkedIn slug→id, normalize.py:57-90) against `seen_urls`, then `title|company` fingerprint (normalize.py:104-112). Note: fingerprint matches *any* historical row, so a re-post of the same role at a new URL after the original expired is still dropped as dup — intended ("don't re-score"), worth knowing. Gov sources opt out via `no_fingerprint` (db.py:304-307).
- **Prefilter** (prefilter.py:131-154): title rules with `title_allow_phrases` protected list, employment type, `max_posted_age_days: 30`, then location. Run 80: 232 of 338 new dropped.
- **Age edge cases**: `age > max` is strict — a job posted exactly 30 d ago passes and expires on day 31 (prefilter.py:157-163, db.py:410-433). All comparisons are timezone-aware UTC; date-only `posted_at` values are treated as UTC midnight, so EU sources (CET dates) can skew ≤1 day inside a 30-day window — benign. The only naive `datetime.now()` in the codebase is `docs.py:371` (letterhead date — cosmetic).
- **Strict-location vs remote column** (prefilter.py:80-129): the source's `remote` flag ORs with remote wording in the string; rule 2 (US) drops remote-US too; rule 3 keeps remote jobs naming only `remote_ok_countries` *unless* hybrid/partial wording appears. Verified consistent with the module docstring and the `test_prefilter_eu_remote.py` suite.
- **Scrape cap**: `todo[:600]` exactly (pipeline.py:188); beyond-budget jobs are still scored from snippets with `low_confidence=1`. No loss.
- **LLM cap**: budget checked per `_chat` (llm.py:214-216); on breach the in-flight job's future raises, `stop=True`, remaining jobs stay `new` (pipeline.py:256-261) — clean boundary, no loss, no overrun.
- **Mid-run throw**: any unhandled exception → run marked `error` + Telegram alert, `pipeline_state` back to idle, lock released in `finally` (pipeline.py:426-445); unscored jobs carry to the next run. No job loss path found.
- **Digest carry-over (6bf0117)**: still present verbatim at pipeline.py:419-424 and still correct for its purpose (shortlists from killed/aborted runs carry into the next digest — it looks back to the last `done` run's `started_at`, so stuck run #22 is correctly skipped). Residual defects in the same window: Bug 3.

---

## 3. Concurrency

- **Storage**: WAL + `busy_timeout=30000` on every pipeline connection (db.py:56-63); dashboard's better-sqlite3 handle uses `busy_timeout = 10000` (dashboard/lib/autojob-db.ts:15). Scoring commits after every finished job; expire link-checks commit per link. Readers never block in WAL.
- **Bug 2 lives here**: `scrape_missing` (pipeline.py:185-201) issues per-job `UPDATE jobs` but commits **once, after the whole loop** — with 600 scrapes at ~1.2-1.5 s each, a write transaction is held for up to ~15 min, twice a day. Any dashboard `UPDATE jobs SET user_action…` (autojob-db.ts:233) during that window blocks 10 s and then throws `SQLITE_BUSY`; a concurrent worker `docs` subprocess (30 s timeout) fails the same way, *after* its LLM calls already ran. Evidence: the pattern is unique to this phase — `expire()` commits per link (expire.py:82), scoring commits per job.
- **user_action collisions**: dashboard writes only `user_action`/`user_action_at`; pipeline writes disjoint columns — no column-level lost updates once the lock issue above is fixed.
- **Worker**: exactly one `autojob-worker.service` (systemd, `Restart=always`), commands executed as fresh subprocesses — a run crash can't take the worker down. `claim_next_command` (db.py:524-531) is SELECT-then-UPDATE without a `status='pending'` guard — not atomic, but with a single poller it can't double-fire (latent only, Bug 7). The `commands` table has seen exactly 1 row ever (a `run`, done) — the worker is nearly idle in practice.
- **Run lock**: PID-based with stale takeover (pipeline.py:96-110) — TOCTOU between read and write is theoretical at 2 runs/day. Timer 06:30/17:30 PDT + ~60-65 min runs + 8 h kill cap = no overlap possible.

---

## 4. Known suspects — verified

| Suspect | Verdict |
|---|---|
| ruff B023 in `ats.py` | **Fixed** at 877686c — lambda binds `job=job` (ats.py:214). `ruff check autojob/`: *All checks passed*. |
| ruff F841 `queued_ids` in `pipeline.py` | **Fixed** — variable removed; `score_jobs` return value discarded (pipeline.py:411-413). |
| Run #22 stuck `running` since 09-09 | **Confirmed in DB**: `runs` row 22, `finished_at` NULL, status `running`. Cause: process killed before the `finally` could close it out; nothing sweeps orphans at startup (Bug 6). Digest logic correctly ignores it (only `done` runs bound the window) — cosmetic + stats pollution only. |
| Digest carry-over fix (6bf0117) still correct after 2.4.0? | **Yes for its purpose** — 877686c didn't touch the window logic. Side effects remain (Bug 3). |
| Empty completions on the free chain | **Gone** — 0 in current logs, errors=0 in runs 67-80 (§1.3). |
| `expire.py` retiring queued-unreviewed jobs | **By design**, bounded, recoverable, acted-on jobs exempt (§2). |

---

## 5. Sources (`sources/*.py`)

- **Silent-zero pattern** (Bug 8): `remoteok.py:21-25`, `gcjobs.py:137`, `hn.py:37`, `boards.py:45`, `adzuna.py:26`, `jooble.py:19`, `workingnomads.py:81`, `yc.py:81` all convert HTTP failures into `return []` with (at best) a log warning — `fetch_all` only records `source_runs.error` when `fetch()` *raises* (pipeline.py:129-136). The eluta precedent is worse: a bot-wall page returns HTTP 200 and `parse_results` simply yields 0 rows with **no log line at all** (eluta.py:71-96). Current data: eluta has 1 zero-fetch run out of 19 since 09-28 with `error=NULL` — today it's noise, but a persistent IP block would present as "healthy source, 0 jobs" indefinitely.
- **Timezones**: every source uses `datetime.now(UTC)` (only docs.py:371 is naive, cosmetic). ✔
- **Memory**: largest observed fetch is workday at 763 jobs/run (log, 2026-10-06); hn pulls `hitsPerPage: 1000`. All bounded lists — no unbounded growth.

---

## 6. Test suite

```
$ venv/bin/python -m ruff check autojob/     → All checks passed!
$ venv/bin/python -m pytest -q               → 1 failed, 125 passed in 9.35s
FAILED tests/test_expiry.py::test_age_rules - assert {1,2,3} == {1,3}
```

All tests build DBs under `tmp_path` (test_expiry.py:12-14) — **production DB untouched**. The failure is a **wall-clock time-bomb**: the test seeds a "fresh" job posted `2026-08-30` and asserts `expire()` keeps it, but `expire()` (expire.py:58-61) calls `D.stale_by_age(conn, …)` **without passing `today`**, while `stale_by_age` has supported an injected clock all along (db.py:410). Today that posting is 37 days old → expired → assertion fails. The suite has been red since ~2026-09-30 and nobody noticed because **there is no CI** (no `.github/workflows`, no pre-push hook) — the "126 tests, ruff clean" claim in the 877686c commit message was true on the morning of 09-29 and silently rotted the next day.

---

## 7. Bug list (ranked by severity)

| # | Severity | Location | Bug | Minimal fix |
|---|---|---|---|---|
| 1 | **High** | `expire.py:58-61` (+ no CI) | `expire()` ignores the injectable clock → test suite red since ~09-30; no CI exists to notice | Add `today: datetime \| None = None` param, pass to `stale_by_age`; add a git pre-push hook or GitHub Actions running `ruff + pytest` |
| 2 | **High** | `pipeline.py:185-201` | Scrape phase holds one write txn up to ~15 min (commit only at line 199); dashboard dismiss/applied (10 s busy_timeout, autojob-db.ts:15/233) and worker docs writes fail with `SQLITE_BUSY` during it, 2×/day | Move `conn.commit()` inside the loop (per scrape), matching `expire.py:82`'s per-link commit |
| 3 | **Medium** | `db.py:383-391`, `pipeline.py:419-424` | Digest window starts at previous done run's `started_at` and `queued_since` has no `user_action` filter → previous run's queued jobs appear in **two consecutive digests**, and dismissed/applied jobs reappear (measured: run 80's digest listed 25 jobs, 17 re-shows from run 79 + 1 already-dismissed; the 71 bulk-dismissed on 10-05 were re-listed in the 10-05 13:38 digest) | `AND user_action IS NULL` in `queued_since`; use `prev["finished_at"]` as the window boundary |
| 4 | **Medium-Low** | `pipeline.py:301` (`generate_docs_for` → `_check_abort`) | A worker `docs` subprocess consumes the run's abort flag (`consume_abort` clears it, db.py:510-517): clicking Abort while docs generate kills the *docs* command and leaves the run running | Check abort only when `summary is not None` (run context) |
| 5 | **Medium** | `pipeline.py:244-285` | No circuit breaker on total LLM failure: provider hard-down → each job walks 7 models × 2 × 90 s timeouts before erroring; ~100-500 candidates → run grinds to the 8 h systemd cap, all jobs `error`, next run repeats | Count consecutive `res is None` results; `stop = True` after ~10 |
| 6 | **Low-Med** | `db.py` `start_run` / nothing at startup | Orphaned `running` runs forever (run #22 since 09-09) — pollutes history/stats | At run start: `UPDATE runs SET status='error', notes='orphaned' WHERE status='running' AND id != ?` |
| 7 | **Low (latent)** | `db.py:524-531` | `claim_next_command` SELECT-then-UPDATE isn't atomic — double execution if a second poller ever exists (manual `autojob worker` alongside the service) | `UPDATE commands SET status='running' … WHERE id=? AND status='pending'`, check `rowcount` |
| 8 | **Low-Med (observability)** | `pipeline.py:129-136` + sources listed in §5 | Fetchers that swallow errors return 0 jobs with `source_runs.error = NULL` — dead sources (eluta IP-block precedent) are invisible | In `fetch_all`, flag `fetched == 0` runs with a warning (or make fetchers raise) |

Nits (no action needed): `runs.scored` includes errors (pipeline.py:253); `set(new_ids)` rebuilt per carried job (pipeline.py:385, O(n·m), negligible at current scale); `openrouter/free` still sits last in the *scoring* chain (search.yaml:105) although the docs chain dropped it for exactly the privacy reason "random router can land on stealth providers — prompts carry the profile"; error jobs retry forever with no cap (§1.5).

---

## 8. Improvement ideas (impact vs effort, ranked)

1. **Add CI (pre-push hook or GitHub Actions: ruff + pytest)** — impact **high** (the suite is red *right now* and nobody knew; would have caught Bug 1 the day it broke), effort **tiny** (~10 lines of YAML or a hook script).
2. **Fix the digest window + acted filter** (Bug 3) — impact **medium-high** (every digest, twice a day: no re-shows of dismissed jobs, no duplicate blocks), effort **tiny** (two one-line changes).
3. **Commit per scrape** (Bug 2) — impact **medium** (removes the only window where dashboard writes can fail), effort **one line**.
4. **Consecutive-error circuit breaker in `score_jobs`** (Bug 5) — impact **medium** (turns an 8-hour grind into a 2-minute graceful stop when OpenRouter is down), effort **~5 lines**.
5. **`expire()` clock injection + fix the test** (Bug 1's code half) — impact **medium** (un-reds the suite, prevents the next time-bomb), effort **tiny**.
6. **Orphan-run sweep** (Bug 6) — impact **low-medium** (clean history/stats), effort **one line**.
7. **Source health surfacing** (Bug 8) — impact **medium over time** (a silently dead source is lost coverage; eluta already went 0-for-one-run unnoticed), effort **small** (zero-fetch streak counter shown on the dashboard).
8. **Optional: free-first-until-N policy using the existing probe** — the probe already knows the bucket; scoring could run free models first while remaining > ~400 and switch to paid below it. Saves ~$0.06/day (credit currently lasts ~10 weeks) at the cost of the 3 s/job free floor and occasional empty completions. **Owner call** — the paid-first latency/reliability rationale is documented and legitimate; only worth it if the credit horizon starts to matter.
9. **Retry cap for `error` jobs** — impact **low** (ends poison-job re-burning), effort **small** (an `attempts` counter or requeue limit).

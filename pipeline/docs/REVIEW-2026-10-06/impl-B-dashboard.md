# Implementation log — Agent B (Dashboard), Phase 1

Repo: `/home/saunalserver/projects/shortlist` · Branch working tree only, **no commits** (orchestrator commits).
Scope respected: `dashboard/**` only; `pipeline/` untouched. Production DBs untouched from manual code (mtimes unchanged: `autojob.db` 07:42 = scheduled run 80, `jobsearch.db` Sep 2); the only prod-DB write is the additive `dismiss_reason` ALTER inside app runtime init, as instructed. All new tests run against `os.tmpdir()` fixtures.

## Item 1 — Keyboard-driven review with auto-advance

**Changed** `dashboard/app/pipeline/jobs/page.tsx`
- Keydown handler in one `useEffect` (jobs/page.tsx:239-311): `j`/`ArrowDown`, `k`/`ArrowUp` move `selectedIdx` through the current page (clamped); `Enter`/`o` open the selected row's panel; `a` = Apply; `d` = Dismiss; `Escape` closes the panel (or confirms a no-reason dismiss when the reason chips are open — see item 2).
- Keys ignored while an `input`/`textarea`/`select` (or contenteditable) is focused; `Enter`/`Space` ignored on focused buttons/links so native activation can't double-fire.
- Row click and keyboard selection share `selectedIdx`; the selected row gets a highlight (jobs/page.tsx:381-391).
- Auto-advance: `openNextPending()` (jobs/page.tsx:118-128) — after a successful Apply/Dismiss the list reloads, the next still-pending row is selected and its panel opened; if none remain on the page the panel closes.
- Handlers wrapped in `useCallback` (clean `exhaustive-deps`, no re-subscribe churn).
- A one-line key hint renders under the action buttons.

**Test:** no DOM test infra exists in this package (no react testing library, no jest/vitest) — adding one would be a new dependency, deliberately skipped. Logic that is testable at the DB layer is covered by `tests/db.test.ts`; UI correctness is covered by lint + tsc.

## Item 2 — One-tap dismiss reasons

**Changed**
- `dashboard/lib/constants.ts:42-51` — canonical `DISMISS_REASONS` list (slugs exactly as specified: `role-family`, `seniority`, `phone-field`, `commute-onsite`, `employer-type`, `bad-data`, `stale`; order = number keys 1-7). Single source shared by UI and server validation.
- `dashboard/actions/autojob.ts:110-118` — `dismissPipelineJob(jobId, reason?)`; validates the slug against `DISMISS_REASONS`, unknown/absent → `null`. Never blocks the dismiss.
- `dashboard/lib/autojob-db.ts:258-261` — `setUserAction(id, action, dismissReason?)` writes `jobs.dismiss_reason` alongside `user_action` (and nulls both when rolling back).
- `dashboard/lib/autojob-db.ts:17-26` — defensive idempotent migration on first connection: `PRAGMA table_info(jobs)` → `ALTER TABLE jobs ADD COLUMN dismiss_reason TEXT` if missing (covers the case where the dashboard container restarts before the parallel pipeline change lands).
- UI (jobs/page.tsx): clicking Dismiss or pressing `d` opens an inline chip row with the 7 reasons (each chip shows its number key); keys `1-7` dismiss with that reason; clicking Dismiss again (button label changes to "Dismiss — no reason"), pressing `d` again, or `Esc` dismisses without a reason. Actioned jobs show the stored reason: "You marked this as dismissed (slug) on …".

**Test:** `tests/db.test.ts` §1 (migration adds the column when the fixture lacks it; idempotent on second call) and §4 (reason persisted, no-reason dismiss leaves NULL, rollback nulls both columns).

## Item 3 — Fourteen-day demote

**Changed** `dashboard/lib/autojob-db.ts`
- `getAutojobJobs` (autojob-db.ts:219-224): when the view is the default pending shape (`status='active'` + `hideActioned` + not `includeStale`), adds `(scored_at IS NULL OR julianday('now') - julianday(scored_at) < 14)`. `julianday` handles both the pipeline's `+00:00` ISO strings and the dashboard's `Z` strings (verified).
- `AutojobJobFilters.includeStale` (autojob-db.ts:88-89).
- `getAutojobStats().pendingReview` (autojob-db.ts:177-182): same exclusion — the overview "To review" card now shows the live queue only (236 → ~56 expected).
- UI: "Show stale (>14d)" checkbox next to "Show actioned" in the jobs header (jobs/page.tsx:349-358) passes `includeStale`.

**Test:** `tests/db.test.ts` §2 — default view returns only the fresh row (total 1); `includeStale: true` returns both; `pendingReview === 1`.

## Item 4 — Low-confidence sort-last

**Changed** `dashboard/lib/autojob-db.ts:241-244` — `ORDER BY COALESCE(low_confidence, 0) ASC, <sortCol> <dir> NULLS LAST, fetched_at DESC` in `getAutojobJobs`. Applies ahead of every sort choice; `COALESCE` keeps NULLs (unscored) in the normal group.

**Test:** `tests/db.test.ts` §3 — score 7 normal sorts above score 9 and 8 low-confidence rows; within the demoted group score order is preserved.

## Item 5 — Apply idempotency + unwedgeable UI

**Changed**
- (a) `dashboard/actions/autojob.ts:89-90` — `promoteJobToTracker` refuses when `jobs.user_action` is already set ("Already marked as … — nothing done").
- (b) `dashboard/lib/db.ts:47-48` — `CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_posting_url ON applications(posting_url)` in the tracker schema init (multiple NULL urls remain allowed by SQLite).
- (c) `dashboard/actions/autojob.ts:92` — `setUserAction(jobId, 'applied')` now runs **before** the tracker insert; if the tracker write throws, the decision is rolled back (`setUserAction(jobId, null)`, autojob.ts:106) so a retry can never leave a half-apply or wedge the job in "applied-but-not-in-tracker". *(Rollback is one step beyond the letter of the task; without it the reorder would trade one stuck state for another.)*
- (d) `dashboard/app/pipeline/jobs/page.tsx:130-176` — `handleApply`/`handleDismiss` (and `handleDocs`) in try/catch/**finally**: buttons always re-enable, failures render as an inline message (`Apply failed: …`), no unhandled rejection.

**Test:** `tests/db.test.ts` §6 — second `createApplication` with the same `posting_url` throws `UNIQUE constraint failed`; NULL urls unrestricted.

## Item 6 — Pending-commands indicator

**Changed** `dashboard/app/pipeline/run-controls.tsx`
- The existing 4 s poll now also calls `fetchPendingCommands` (run-controls.tsx:19-37); when any command is pending/running a badge renders in the RunControls row: `run queued 2m` / `run — worker executing` (multiple commands joined). Tooltip names the failure mode: worker down → `systemctl --user status autojob-worker`. Age is computed inside the poll callback (React purity rule forbids `Date.now()` during render).

## Item 7 — score_facts display

**Changed**
- `dashboard/lib/autojob-db.ts:57` — `score_facts: string | null` added to `AutojobJob` (both queries are `SELECT *`, so no SQL change needed).
- `dashboard/app/pipeline/jobs/page.tsx:10-22` — `parseScoreFacts()`: JSON.parse in try/catch, only scalar entries of a plain object become chips; anything else (invalid JSON, arrays, nested objects, NULL) renders nothing.
- Panel renders a compact `key: value` chip row after the meta line (jobs/page.tsx:478-487). Today it is NULL everywhere — invisible until scoring v2 populates it.

## Item 8 — Expiry pressure line

**Changed**
- `dashboard/lib/autojob-db.ts:264-277` — `getExpiringPendingCount(withinDays=3)`: one query, `status IN ('queued','docs_generated') AND user_action IS NULL` and within 3 days of either limit — `julianday('now') - julianday(substr(posted_at,1,10)) >= 30-?` when a posting date parses, else the 45-day `fetched_at` limit — mirroring `stale_by_age` in `pipeline/autojob/db.py` (30/45 come from `search.yaml expiry`; hardcoded here with a comment, as the dashboard already does elsewhere).
- `dashboard/actions/autojob.ts:57-60` — `fetchExpiringPendingCount` server action.
- Jobs header (jobs/page.tsx:359-363): "⏳ N pending jobs retire within 3 days" (hidden when 0), tooltip explaining the limits.

**Test:** `tests/db.test.ts` §5 — 29d-posted counted, 5d not, no-posting-date + 44d-fetched counted, already-actioned and already-expired excluded → 2.

## Item 9 — Tracker outcome loop

**Changed**
- (a) `dashboard/lib/constants.ts:33-39` — `QUICK_STATUSES = [screening, interview, offer, rejected, ghosted]` (statuses already existed). `dashboard/components/applications/application-table.tsx:57-65, 128-150` — one-click status chips under the status badge in the full (non-compact) table; click → `updateExistingApplication(id, {status})` (which bumps `updated_at`), parent state updated in place via new optional `onUpdated` prop, wired in `dashboard/app/table/page.tsx:110-113`. Current status chip is disabled/highlighted.
- (b) `dashboard/actions/autojob.ts:93` — `getOrCreateCompanyByName(job.company)` (already existed in `lib/db.ts`, lowercased-name upsert) on every promote. *Deliberate deviation: hooked into `promoteJobToTracker` (the autojob path, which is the only place "the job company" exists) rather than inside shared `createApplication`, so manual tracker entries don't silently start creating company rows.* Reused the existing helper instead of writing a new upsert.
- (c) `dashboard/actions/autojob.ts:102` — `source: job.source || 'other'` instead of hardcoded `'other'`. `dashboard/lib/types.ts:11` — `ApplicationSource` widened with `(string & {})` so pipeline slugs (wttj, ats_companies, …) are honest in the type while keeping autocomplete; `dashboard/lib/constants.ts:70-71` — `sourceLabel()` helper with raw-slug fallback; `dashboard/app/api/export/csv/route.ts:3,26` — CSV export uses it (previously would have printed "undefined").

**Test:** `tests/db.test.ts` §6 — `getOrCreateCompanyByName('Acme Corp')` + `'ACME CORP'` → one company row named `Acme Corp`.

## Item 10 — README fix

**Changed** `dashboard/README.md:27` — now states check-reminders runs via the **system-level** unit `/etc/systemd/system/check-reminders.{service,timer}` (copies of the `scripts/` files, not symlinks). Matches report 04 §3 and dashboard/CLAUDE.md.

## Item 11 — lint + tsc

`cd dashboard && npm run lint` → **exit 0, 0 errors** (3 warnings remain — all pre-existing at baseline: unused vars in pdf route, quick-add-dialog, company-form). `npx tsc --noEmit` → **exit 0**.

**Important baseline finding:** lint was already red at HEAD before my changes — 5 errors, verified by eslint against a `git archive HEAD` copy:
- `app/pipeline/logs/page.tsx`, `app/table/page.tsx`, `components/applications/application-panel.tsx` — `react-hooks/set-state-in-effect` (eslint-plugin-react-hooks v6 / react-compiler rules; no CI exists to have caught this).
- `lib/autojob-db.ts` — `require('fs')` inside `getSerperCredits` (`no-require-imports`).

Since item 11 requires green, each got the minimal canonical fix, all inside my owned area:
- `app/pipeline/logs/page.tsx:27-35` — initial fetch inlined into its effect with an `alive` guard (the rule flags setState reached synchronously through the shared `load` callback).
- `app/table/page.tsx:22-49` — derived `filteredApplications` effect+state replaced by `useMemo` (behavior-identical).
- `components/applications/application-panel.tsx:13,18` — removed the synchronous `setIsLoading(true)` from the effect (initial state now `true`).
- `lib/autojob-db.ts:7,329` — `import fs from 'fs'` at module top instead of `require()`.
Plus my own additions were kept warning-clean (handlers in `useCallback`; age computed in the poll callback, not render).

## Tests added

`dashboard/tests/db.test.ts` (new; plain `node:assert` run via the already-installed `tsx` — no new dependencies, no framework) + `"test": "tsx tests/db.test.ts"` in `package.json`. Fixture = throwaway sqlite files in `os.tmpdir()`; the jobs fixture is created **without** `dismiss_reason` so the defensive migration is exercised for real. Covers: migration, 14-day demote (list + stats + toggle), low-confidence sort-last, dismiss reason writes + rollback, expiry count, tracker unique index, company upsert.

## Commands run (all from `dashboard/`)

| Command | Result |
|---|---|
| `npm test` | pass (6 sections) |
| `npm run lint` | exit 0, 0 errors, 3 pre-existing warnings |
| `npx tsc --noEmit` | exit 0 |
| `eslint` on `git archive HEAD` copy | baseline proof: 5 pre-existing errors |

## Deliberately skipped

- DOM-level tests for the keyboard handler/chips — no React test infrastructure in this package; adding one is a new-dependency decision for the orchestrator.
- Digest-side stale/low-confidence exclusion — pipeline side, owned by the parallel agent.
- Kanban/home-page quick chips — home uses `compact` mode; chips only on `/table`.
- Docker rebuild — explicitly deferred to the orchestrator.
- Auto-pagination in auto-advance when the last pending row of a page is actioned (panel simply closes; `Next` remains one click).

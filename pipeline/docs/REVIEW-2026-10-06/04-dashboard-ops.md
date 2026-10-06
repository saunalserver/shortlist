# Slice 4 — Dashboard & Operations (read-only review, 2026-10-06)

Scope: `dashboard/actions/`, `dashboard/lib/`, `dashboard/app/pipeline/`, `dashboard/scripts/check-reminders.ts`, live systemd/docker state, backups. All DB access via `mode=ro` URIs. No files mutated.

---

## 1. How Apply / Dismiss are actually saved

### The write path (traced)

1. **Button** — review panel in `dashboard/app/pipeline/jobs/page.tsx:433` (`Apply — promote to tracker`) / `:440` (`Dismiss — not a fit`), both `disabled={actioning}` (client-side guard, `page.tsx:51`).
2. **Handler** — `handleApply` (`page.tsx:87`) → server action `promoteJobToTracker` (`dashboard/actions/autojob.ts:80`).
3. **Two separate databases, two separate writes** (`actions/autojob.ts:84–95`):
   - `createApplication({...status:'applied', source:'other', tags:['autojob',source]})` → **tracker DB** `dashboard/data/jobsearch.db` (`dashboard/lib/db.ts:115` INSERT, schema at `db.ts:18–45`).
   - then `setUserAction(jobId,'applied')` → **pipeline DB** `UPDATE jobs SET user_action=?, user_action_at=?` (`dashboard/lib/autojob-db.ts:232`).
4. **Dismiss** is a single write: `dismissPipelineJob` → `setUserAction(jobId,'dismissed')` (`actions/autojob.ts:102–104`). No reason is captured anywhere — there is no `dismiss_reason` column (schema `pipeline/autojob/db.py:110–128`).
5. **The worker/commands queue is NOT involved in Apply/Dismiss.** The `commands` table (`db.py:201–210`) only carries `run` / `docs` / `abort`, enqueued by `triggerAutojobRun`/`requestDocs` (`dashboard/lib/autojob-db.ts:230`, `actions/autojob.ts:53–78`) and executed by `pipeline/autojob/worker.py` (`claim_next_command`/`finish_command` at `db.py:524–538`; subprocess-per-command so crashes never kill the worker, `worker.py:1–8, 27–45`).

### Failure modes found

| # | Mode | Evidence | Severity |
|---|------|----------|----------|
| F1 | **Double-apply has no server-side guard.** `promoteJobToTracker` never checks `jobs.user_action` before inserting the tracker row; two tabs, a retry, or the F2 window below → two tracker rows. No unique index on `applications.posting_url` (schema `lib/db.ts:18–45`). Today: 18 tracker rows, 0 duplicate URLs — hasn't happened *yet*. | `actions/autojob.ts:80–95` | Medium |
| F2 | **Half-failed Apply.** Tracker insert runs *before* `setUserAction`. If `setUserAction` throws (e.g. SQLITE_BUSY past the dashboard's 10 s busy timeout, `autojob-db.ts:14–15`), the action reports "Failed" but the tracker row already exists; the job stays pending; clicking Apply again creates a second row. | `actions/autojob.ts:84–95` ordering | Medium |
| F3 | **Optimistic UI can wedge.** `handleApply`/`handleDismiss` (`page.tsx:87–109`) have no try/catch — if the server action throws, the awaited promise rejects, `setActioning(false)` never runs, and both buttons stay disabled ("Applying…") until reload. No error message is shown. | `page.tsx:87–109` | Medium |
| F4 | **Command queued while worker down = silent stall.** `triggerAutojobRun` says "the worker picks it up within a few seconds", but `fetchPendingCommands` (`actions/autojob.ts:38`) is exported and **used nowhere in the UI** (grep: zero usages in `app/`+`components/`). History shows the worker can be down for hours: 2026-09-13 13:45–13:46 journal shows a crash-loop (203/EXEC after venv rebuild, then `EOFError: marshal data too short`) before recovery. A queued `run` would sit `pending` with no indicator. | `journalctl --user -u autojob-worker.service`; grep | Medium |
| F5 | **Dashboard ↔ pipeline concurrency: actually fine.** Both DBs are WAL (`PRAGMA journal_mode` → `wal`). Python side: WAL + `busy_timeout=30000` (`pipeline/autojob/db.py:59–62`); dashboard side: `busy_timeout = 10000` (`dashboard/lib/autojob-db.ts:14–15`). Docker bind-mounts the *whole* pipeline dir so `-wal`/`-shm` are shared (`dashboard/docker-compose.yml:9–10`). Dashboard writes are single short statements (`user_action` row UPDATE, `commands` INSERT) — WAL serializes writers; lost-update risk is negligible. | as cited | Low |
| F6 | **Stuck commands: none today.** `commands` has exactly **1 row ever** (id 3, `run`, done 2026-09-03). Zero pending/running. Note: the dashboard's "Generate tailored resume + cover letter" button (`page.tsx:401`) has **never been used** — all 16 `docs_generated` jobs came from scheduled runs (`pipeline/autojob/pipeline.py:289–318`). | `sqlite3 … "SELECT … FROM commands"` | Info |

Also noted: `pipeline_state` has a dashboard-side 4 h stale-"running" guard (`autojob-db.ts` `getPipelineState`), and the state row is healthy (`idle`, run 80).

---

## 2. Review-screen ergonomics

**What the reviewer sees per job** (slide-over panel, `page.tsx:330–465`): title, company, score badge, status, location, employment type, salary range, posted date, source, low-confidence flag, URL, full description (collapsed `<details>`), `fit_reasoning`, `strengths`, `gaps`, `prefilter_reason`/`skip_reason`, PDF links (or generate-docs button), fetched/scored timestamps + scorer model. **`score_facts` is stored by the pipeline** (column added `pipeline/autojob/db.py:125`, populated with the score breakdown at `pipeline.py:262`) **but never selected or displayed by the dashboard** — the `AutojobJob` type (`lib/autojob-db.ts:17–47`) doesn't even include it. The structured scoring evidence is invisible to the only person making decisions with it.

**Table & filters** (`page.tsx:139–186`): search (title/company/location), status (default `active` = queued+docs_generated), min-score 1–10, sort by fit_score / posted_at / scored_at (desc only), 25 rows/page, "Show actioned" toggle. Actioned rows dim to 40 % opacity but stay in place.

**The decision loop is 5 clicks per job**: click row → panel opens → read → click Apply/Dismiss → close panel (✕ or backdrop) → find/click next row. **Zero keyboard shortcuts** (grep for `onKeyDown|keydown|useHotkey` across `app/`, `components/`, `store/`: no matches). No auto-advance to next pending job after an action. No bulk select. No session timer/pomodoro, no per-session counters. The zustand store (`store/ui-store.ts`) only tracks tracker-panel/quick-add/filter state — nothing for the review loop.

**How the bulk dismissals actually happened** (from `user_action_at` timestamps):

| Date | Count | Evidence | Verdict |
|------|-------|----------|---------|
| 2026-09-12 | **352** | **301 share the same millisecond** `2026-09-12T03:51:07.873Z` and **all 301 are `fit_score = 6`** (min=max=avg=6.0); the other 51 spread 00:06–21:19 UTC across 5 h | 301 = **one direct SQL UPDATE** — the recalibration cleanup after `min_score_to_queue` went 6→7; the rest were clicks |
| 2026-10-05 | 71 | spread 18:38–21:01 across 4 h, max 9/min, no duplicate timestamps | **manual UI session**, same evening as 8 applies (79 decisions ≈ 2.5 h ≈ 30–50/h) |
| 2026-09-28 | 45 | 18:06–19:12, 2 distinct hours | manual evening session |
| 2026-10-03 | 11 | 18:29–18:57, 1 hour | manual evening session |

So: **no bulk UI exists**; the one true bulk dismissal was raw SQL, which is why it has no reasons and a single timestamp. `autojob action <id> applied|dismissed` exists as a per-job CLI (`pipeline/autojob/cli.py:197–200`), not bulk.

**The "829 backlog" is really 236.** `queued`=829 includes 579 dismissed + 14 applied that keep status `queued` forever (status is never rewritten on action). The dashboard's "To review" stat (`pendingReview`, `lib/autojob-db.ts:172–174`: `status IN ('queued','docs_generated') AND user_action IS NULL`) = **236 pending** — 230 at score 7, 6 at score 8; 212 fetched in September, 24 in October. Age pressure: by `posted_at`, 22 are 0–14 d, **107 are 15–30 d**, 1 >30 d, 106 unknown — with expiry at `posted_max_days=30` / `fetched_max_days=45`, unreviewed September jobs will retire out from under the queue (121 jobs already `expired` with no user action). The backlog is visible on the overview page as a single number and inside the jobs table as pagination (236/25 ≈ 10 pages); nothing communicates "these expire soon."

---

## 3. check-reminders

**Logic** (`dashboard/scripts/check-reminders.ts`): stale = `applied` with `julianday(now) − updated_at ≥ 14` or `screening ≥ 7` (query at `:112–128`); one nudge per app per 14 d, hard ghost-cutoff at 60 d (`:235–247`); dedupe state in `dashboard/data/reminders-sent.json`; Telegram send with 429 backoff and 3 retries (`:141–190`). Reads the tracker DB **readonly** (`:222`). Sound overall. Two notes: staleness is measured from `updated_at`, so *any* edit (a typo fix in notes) resets the clock; and the state file never prunes (harmless at 18 apps).

**Deployment — it IS running, but not where the docs say.** `dashboard/README.md:27` claims a *user* unit "symlinked from scripts/". Reality: installed as a **system-level** unit, `/etc/systemd/system/check-reminders.{service,timer}` (root-owned, byte-identical to the repo copies), timer **active**, `OnCalendar=09:00 America/Vancouver`, `Persistent=true`. Last run today 09:00:01 — "Found 8 stale application(s) … Sent: 0" (4 were nudged 2026-10-03, still inside their 14 d window; journal confirms sends on Oct 3). Next fire Oct 7 09:00.

**The real weakness is upstream data, not the script**: all 18 tracker applications are still `status='applied'` — nothing has ever moved to screening/interview/rejected/ghosted (statuses exist in `lib/constants.ts:3–13`, kanban board exists). So every app inevitably crosses 14 d and gets nagged every two weeks until the 60 d ghost cutoff; the reminders measure tracker hygiene, not real follow-up state.

---

## 4. Live ops state (read-only checks, 2026-10-06 ~11:00 PDT)

| Check | State | Verdict |
|-------|-------|---------|
| `autojob.timer` (user) | Active; `OnCalendar=06:30 & 17:30 America/Vancouver` + `RandomizedDelaySec=10m`, `Persistent=true` (task brief said 07:00/19:00 — actual is 30 min earlier). Next fire today 17:35. | 🟢 |
| `autojob.service` | Last run today 06:39–07:44, exit 0, CPU 5 min. Run 80: 5,495 fetched / 338 new / 106 scored / 8 queued / **0 errors** in 65 min. Runs 75–80 (Oct 4–6): all `done`, 57–66 min, 0 errors, 0 docs. | 🟢 |
| `autojob-worker.service` | Active since Sep 6 boot, 6.5 MB RSS. Journal since boot: only "worker started (poll 3s)" — **it has executed exactly 1 command ever** (2026-09-03). Historical: Sep 13 3 h crash-loop (venv rebuild → 203/EXEC → marshal EOFError) — self-healed via `Restart=always`. | 🟢 (idle, not broken) |
| `check-reminders.timer` | System-level, active, fired today 09:00. | 🟢 |
| Dashboard container | `dashboard-jobsearch-1`, up 8 days, port 3100 → HTTP 200. Image built 2026-09-06 18:35 UTC ≈ commit `b4c0a80` — the **last commit touching `dashboard/`**, so the running image is current (Sep 28–29 commits are pipeline-only). | 🟢 |
| Dashboard logs (7 d) | Only recharts `width(-1)/height(-1)` warning spam (CSS sizing in charts); zero errors/exceptions. | 🟡 cosmetic |
| `pipeline_state` | `idle`, run 80 done, pid stale but harmless. | 🟢 |
| Run-source warnings | Recurring every run: `remoterocketship` 404 (dead query), occasional himalayas 503, TELUS read-timeout. All retried/skipped, runs finish clean. | 🟡 tune later |

Nothing red in live state. The red items are structural (below).

---

## 5. Backups — covered, weekly, with two caveats

**Yes, both DBs are covered** — by the homelab-wide weekly backup, not by anything shortlist-specific:

- `cloud-backup.timer` (user, Mon 05:00, `Persistent`) → `/home/saunalserver/scripts/cloud-backup.sh`: tars **`$H/projects`** (line ~205 of the include list) into a 2.4 G `homelab-backup-YYYYMMDD.tar.gz`, uploads via rclone to Proton Drive, verifies, **keeps last 4** (~4 weeks). Last success: **2026-10-05 05:31** ("Upload verified successfully", log `/var/log/cloud-backup.log`).
- The tar includes `pipeline/data/autojob.db` (109 M + 8.4 M WAL) and `dashboard/data/jobsearch.db` (32 K + 316 K WAL) — only `*.log`, caches, `node_modules`, `venv`, `.git` are excluded.
- Git does **not** cover them (`.gitignore`: `data/`, `*.db`). Only other copy: a manual `autojob.db.bak-2026-09-02` (17 M, pre-growth snapshot).

**Caveat 1 — consistency:** the script uses `sqlite3 '.backup'` for Vikunja/Navidrome/Kuma precisely because tarring a live WAL DB can be inconsistent — but the shortlist DBs are just tarred in place. Mitigating factor: Monday 05:00 sits in the gap between the 17:30 and 06:30 runs, so write pressure is ~zero. Still, the correct pattern is already in the script; shortlist just wasn't added to the consistent-copy list.

**Caveat 2 — RPO if the disk dies tonight: up to 7 days, currently ~30 h.** Last backup is Mon Oct 5 05:00. **Not in any backup: the entire Oct 5 evening review session** — 8 tracker applications created 18:45–20:31 (hand-picked by Victor, the project's most valuable rows), 71 dismissals, and everything today. Weekly cadence for a manually-curated tracker is the single biggest ops risk in this project.

---

## 6. Improvement ideas (impact vs effort, ranked)

1. **Daily consistent backup of both SQLite DBs** — add `sqlite3 …autojob.db ".backup …"` + `…jobsearch.db` to an existing daily path (or a tiny `shortlist-backup.timer` mirroring the script's own sqlite step, pushing to `/mnt/photos` or Proton). Impact: **critical** (tracker RPO 7 d → 1 d); Effort: **S** (~10 lines + one timer).
2. **Keyboard-driven review with auto-advance** — j/k or ↑/↓ to move rows, `a`=apply, `d`=dismiss, auto-open next pending job after each action; a small `useEffect` keydown handler in `jobs/page.tsx`. Impact: **high** (the loop is 5 clicks/job today; observed ~30–50 decisions/h → plausibly 2–3×); Effort: **S–M**.
3. **Capture dismiss reasons** — one new column (`dismiss_reason`), a 6-chip taxonomy (salary / location / seniority / not-remote / company / dupe) with keys 1–6 in the same shortcut handler. Turns 591 dismissals into a tuning signal for prefilter/scoring instead of a black hole. Impact: **high**; Effort: **M**.
4. **Server-side idempotency + error handling for Apply** — guard `promoteJobToTracker` on `user_action IS NULL`, add a unique index on `applications.posting_url`, and wrap `handleApply`/`handleDismiss` in try/catch so the panel can't wedge on "Applying…". Impact: medium (prevents dup rows / stuck UI); Effort: **S**.
5. **Pending-commands + worker heartbeat in the UI** — `fetchPendingCommands` already exists; surface it in `RunControls` (e.g. "queued 2 min ago — worker last seen …"). Catches the worker-down silent-stall mode (F4). Impact: medium; Effort: **S**.
6. **Show `score_facts` in the review panel** — data is already in the DB; add it to the SELECT + type + panel. Impact: medium (better decisions, scorer auditability); Effort: **S**.
7. **Bulk-dismiss UI with reason** — "dismiss all pending below score X / older than Y with reason Z" as a guarded server action, replacing the raw-SQL recalibration cleanups. Impact: medium-high (next recalibration is inevitable); Effort: **M**.
8. **Expiry pressure made visible** — digest/panel line "N pending jobs retire in the next 3 runs" (107 of 236 are already 15–30 d old). Impact: medium; Effort: **M**.
9. **Tracker status hygiene loop** — after Apply, the tracker row sits at `applied` forever; add a quick "moved to screening / ghosted" action (or a reply-to-Telegram-reminder flow) so check-reminders reflects reality instead of nagging everything. Impact: medium; Effort: **M**.
10. **Doc/log polish** — fix `dashboard/README.md:27` (check-reminders is a system unit, not a user symlink); fix the recharts responsive-container sizing to stop log spam; drop the dead `remoterocketship` query that 404s every run. Impact: low; Effort: **S**.

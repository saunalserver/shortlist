# job-search-command-center — agent notes

Next.js dashboard (:3100, Docker container `job-search-command-center-jobsearch-1`, `docker compose up -d --build`).
Companion to `~/projects/Autojob-search` (the Python pipeline). Read that repo's CLAUDE.md for the data model.

- Tracker data: `data/jobsearch.db` (git-ignored). Pipeline data: read from the mounted Autojob repo at `/app/autojob-source/data/autojob.db`.
- The container cannot run Python. UI actions that need the pipeline (`Run now`, `Generate documents`) insert into the
  `commands` table; `autojob-worker.service` (user systemd unit on the host) executes them. Abort also goes through the queue.
- Your Apply/Dismiss decisions are stored in `jobs.user_action` in the pipeline DB (not in a separate table).
- `scripts/check-reminders.ts` → system timer `check-reminders.timer` (09:00). Telegram creds come from `../Autojob-search/.env`.
- Removed 2026-09-01: Apollo recruiter finder, `pipeline_actions`/`pipeline_jobs` archive tables, `.env` editing from the UI,
  `sync-autojob-data` copy job, agent planning docs. History: tag `legacy-2026-09-01`.
- After changing code: `npm run lint && npm run build`, then `docker compose up -d --build`.

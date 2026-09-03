# Job Search Command Center

Personal dashboard for a job hunt. Two halves:

1. **Tracker** — applications kanban/table, companies, CSV/JSON export, daily Telegram nudge for stale applications.
2. **Pipeline** — review queue for the jobs the [Autojob](../Autojob-search) pipeline scored, with one-click *Apply* (creates a tracker entry), *Dismiss*, and *Generate tailored resume + cover letter*.

Next.js 16 · React 19 · Tailwind 4 · better-sqlite3. Runs as a Docker container on port 3100.

## How it talks to the pipeline

The container bind-mounts the `Autojob-search` repo and reads its SQLite database (`data/autojob.db`), logs and
generated PDFs directly. It never runs Python: "Run now" and "Generate documents" write a row into the
`commands` table, and the host-side `autojob worker` service (systemd, user unit) executes it within seconds.
Your decisions are written back to `jobs.user_action`, so the pipeline knows what you already looked at.

## Run

```bash
docker compose up -d --build      # http://<host>:3100
```

Local dev: `npm install && npm run dev` (reads `../Autojob-search/data/autojob.db` by default; set `AUTOJOB_DB_PATH` / `AUTOJOB_PROJECT_ROOT` to override).

## Reminders

`scripts/check-reminders.ts` runs daily at 09:00 via the system unit `check-reminders.timer` (symlinked from `scripts/`).
It nudges on Telegram for applications stuck in *applied* ≥14 days or *screening* ≥7 days, once per application per 14 days,
and stops nagging after 60 days (assume ghosted).

## Layout

```
app/            routes (dashboard, kanban, table, companies, pipeline/*)
actions/        server actions (applications, companies, autojob)
components/     UI
lib/db.ts       tracker database (data/jobsearch.db)
lib/autojob-db.ts  read access to the pipeline database + command queue
scripts/        reminder script + systemd units
```

# autojob — agent notes

Python package `autojob/` (see README for the user-facing picture). Rebuilt 2026-09-01; the previous flat-file version is
tagged `legacy-2026-09-01` and its two forks are branches `feature/shareable-v2` and `legacy/shareable`.

## Layout
- `autojob/pipeline.py` — the run: fetch → insert/dedupe → prefilter → scrape → score → auto-docs → digest. Sequential; abort via `pipeline_state.command`.
- `autojob/sources/*.py` — one module per source, `fetch(settings) -> list[RawJob]`. Registry in `sources/__init__.py`. `ats.py` is shared Greenhouse/Lever/Ashby logic.
- `autojob/db.py` — schema v3 (+ v1/v2 migrations). **Jobs are never deleted.** `seen_urls` is the dedup set; `fingerprint` (title|company) catches cross-source dupes.
- `autojob/prefilter.py` — rule-based rejection, configured in `config/search.yaml: prefilter`. Keep it high-precision. `location_reason()` is shared with the company-board sources; `title_allow_phrases` protects target titles ("chief of staff") from the exclusion words.
- `autojob/expire.py` — retires shortlisted jobs (status `expired`): age rule + posting-page check (404 / "no longer accepting"). Runs first in every `run`; `autojob expire` for manual use. Config: `expiry:` in search.yaml.
- `autojob/llm.py` — model fallback list with per-model pacing and **cooldowns** (503/timeout → 90 s sit-out, next model takes the call); strips Gemma `<thought>` blocks; `chat_json` / `chat_text`. `LLMBudgetExceeded` must propagate out of the scorer (it stops the loop; leftovers stay `new`).
- `autojob/scorer.py`, `prompts/scorer.md` — scoring. `{candidate_profile}` is replaced with `profile/candidate.md`.
- `autojob/docs.py` — nothing is written in LaTeX by the model. Resume: `parse_resume` splits the template into summary + `\resumeItem` bullets per `\resumeSubheading`; the model returns a bullet order (+ optional drop) and a new summary, `summary_is_grounded` rejects summaries citing numbers/tools not in the template, overflow drops trailing bullets deterministically. Cover letter: model JSON → `profile/cover_letter.tex` placeholders. `keep_template_preamble` is kept for the legacy path.
- `autojob/notify.py` — one Telegram message per run. `autojob/worker.py` — consumes the `commands` table written by the dashboard; each command runs as a fresh `python -m autojob …` subprocess, so code changes apply without restarting the service (only edits to `worker.py` itself need `systemctl --user restart autojob-worker.service`).
- `autojob/cli.py` — `autojob run|docs|sources|companies|expire|stats|action|worker|doctor`.
- Sources worth knowing: `workday.py` (public `wday/cxs` API, tenants in search.yaml, checks `seen_urls` before fetching a description), `eluta.py` (HTML search results only — job pages are bot-walled, so `scraper.BLOCKED` includes eluta.ca).

## Runtime on this server
- venv: `./venv` (`pip install -e ".[dev]"`). Tests: `venv/bin/pytest -q`. Lint: `venv/bin/ruff check autojob tests`.
- Data: `data/autojob.db`, `data/autojob.log`; PDFs in `output/`. Profile + templates in `profile/` (git-ignored, personal data).
- systemd **user** units: `autojob.timer` (07:00 America/Vancouver) → `autojob.service`; `autojob-worker.service` (always on).
  `systemctl --user status autojob.timer autojob-worker.service`. Logs: `journalctl --user -u autojob.service`.
- Dashboard: `~/projects/shortlist/dashboard` (Docker :3100) mounts this directory read/write.
- Secrets in `.env`. Serper key rotated 2026-09-01; Gemini/Telegram/Adzuna/Jooble keys were in git history until 2026-09-01 and should still be rotated.

## Gotchas
- Serper free tier: `num` ≤ 10 and no `gl`/`hl` parameters, or every query returns 400 "Query pattern not allowed".
- Himalayas returns 403 to browser-like User-Agents; the source sends a plain one.
- Gemini `gemini-3.5-flash-lite` sometimes 503s under load; the fallback list handles it. Gemma models wrap output in `<thought>`.
- `autojob companies verify` lists dead ATS slugs; remove them from `search.yaml` (33 pruned on 2026-09-01).
- Job Bank ignores the location parameter; the prefilter's province rules `(qc)`, `(on)`… do the filtering.
- Don't run two pipelines at once: `data/autojob.lock` holds the PID; stale locks are taken over automatically.
- The digest selects jobs by `scored_at >= run start`, not `run_id` — carry-over jobs have an older `run_id`.
- Schema v3 (2026-09-02): `jobs.link_checked_at`, `runs.expired`, fingerprints use a two-word company key (recomputed on upgrade).
- Adzuna uses `title_only`; switching back to `what` multiplies the fetch by ~10 with almost no extra relevant jobs.
- Workday: `limit` > 20 returns nothing; site names are case-sensitive and differ per tenant (`ubcstaffjobs`, `External`, `External_Careers`).

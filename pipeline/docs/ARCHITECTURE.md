# Architecture

```
            ┌──────────── sources/ (13 modules, isolated, budgeted) ────────────┐
            │ boards(LinkedIn/Indeed) adzuna jooble jobbank serper remotive     │
            │ remoteok jobicy themuse weworkremotely himalayas ats_companies yc │
            └───────────────────────────┬──────────────────────────────────────┘
                                        ▼  list[RawJob]
                     canonical_url + fingerprint(title|company)  → db.insert_jobs
                                        ▼  status=new
                     prefilter.py (rules from search.yaml)        → status=prefiltered
                                        ▼
                     scraper.py (only if description < 200 chars, budgeted)
                                        ▼
                     scorer.py + llm.py (model fallback list)     → status=skipped | queued
                                        ▼
                     docs.py for fit_score ≥ auto_docs_min_score   → status=docs_generated
                                        ▼
                     notify.py — one Telegram digest
```

## Data model (`data/autojob.db`)

| Table | Purpose |
|---|---|
| `jobs` | one row per canonical URL. `status` ∈ new / prefiltered / skipped / queued / docs_generated / error. `user_action` ∈ applied / dismissed (written by the dashboard or `autojob action`). Never deleted. |
| `seen_urls` | every URL ever fetched (dedup set, survives everything) |
| `company_ats_cache` | company slug → greenhouse / lever / ashbyhq / none, 30-day TTL (negatives cached too) |
| `runs`, `source_runs` | per-run and per-source counters (dashboard "Recent runs" and "Sources") |
| `pipeline_state` | single row: status, phase, progress, `command='abort'` flag |
| `commands` | queue written by the dashboard: `run` (arg `dry`), `docs` (arg job id), `abort`; consumed by `autojob worker` |

## Processes

- `autojob.timer` → `autojob run` once a day.
- `autojob-worker.service` polls `commands` every 3 s and executes them in-process (the dashboard container has no Python or TeX).
- Both use `data/autojob.lock` (PID file) so they never run a pipeline concurrently.

## Why these choices

- **SQLite + never delete**: dedup and "score once" fall out of a UNIQUE constraint. The old cleanup-then-refetch loop re-scored ~550 jobs a day.
- **Prefilter before LLM**: model calls are the scarce resource (free tier RPD). Rules are high-precision on purpose; ambiguity goes to the model.
- **Model fallback list with per-model RPM**: Gemini free tier throttles per model; three lite models + Gemma cover a day comfortably.
- **On-demand docs**: generation is the slowest, most expensive step (2–3 model calls + pdflatex ≈ 1–3 min per job) and most output was never used.
- **Cover letter as JSON → template**: the model can't break LaTeX; length is controlled; the personal header stays exact.
- **Command queue instead of spawning Python from the UI**: works across the container boundary and survives restarts.

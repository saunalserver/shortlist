# autojob

An automated job search that runs every morning and hands you a short list worth your time.

1. **Fetch** postings from 13 sources: LinkedIn + Indeed (via JobSpy), Adzuna, Jooble, Job Bank Canada, Google (Serper, budgeted),
   Remotive, RemoteOK, Jobicy, The Muse, We Work Remotely, Himalayas, ~150 company career pages (Greenhouse / Lever / Ashby
   public APIs) and every Y Combinator company that is hiring.
2. **De-duplicate** by canonical URL and by title + company, across sources and across days — a posting is scored once, ever.
3. **Prefilter** with cheap rules (seniority words, wrong professions, wrong city, internships). Costs nothing; removes roughly
   half of what is left before any model call.
4. **Score** each remaining job 1–10 against your candidate profile with an LLM (Google Gemini free tier by default, any
   OpenAI-compatible endpoint works). Strict, calibrated prompt; hard disqualifiers and soft penalties are explicit.
5. **Shortlist** jobs at or above your threshold. Generate a tailored LaTeX resume + cover letter automatically only for the
   top scores; everything else on demand, when you actually decide to apply.
6. **Notify**: one Telegram digest per run with score, company, title, one-line rationale and links.

A companion dashboard ([dashboard](../dashboard)) shows the review queue, lets you apply /
dismiss / generate documents, tracks your applications, and shows per-source health.

## Quick start

```bash
git clone <this repo> && cd autojob
./scripts/install.sh --no-systemd        # venv + deps + folders (+ systemd user units without the flag)
cp .env.example .env                     # add LLM_API_KEY (https://aistudio.google.com/apikey) and optional source keys
$EDITOR profile/candidate.md profile/resume.tex profile/cover_letter.tex
$EDITOR config/search.yaml               # queries, city, thresholds, sources on/off
./venv/bin/autojob doctor                # checks keys, TeX, profile files
./venv/bin/autojob sources test adzuna jobicy   # try a couple of sources
./venv/bin/autojob run --dry-run --max-jobs 20  # full pipeline on 20 jobs, no docs, no Telegram
./venv/bin/autojob run                          # the real thing
```

Requirements: Python 3.11+, `pdflatex` (TeX Live or TinyTeX) and `pdfinfo` (poppler) for the documents.

## Commands

| Command | What it does |
|---|---|
| `autojob run [--dry-run] [--sources a,b] [--max-jobs N] [--no-docs] [--no-notify]` | The daily pipeline |
| `autojob docs <job_id>…` | Generate resume + cover letter for specific jobs |
| `autojob sources list` / `autojob sources test [names…]` | Show / try sources |
| `autojob companies verify` / `autojob companies probe <name>…` | Check the ATS slugs in `search.yaml` / find a company's ATS |
| `autojob expire [--dry-run] [--links N]` | Retire shortlisted postings that are too old or whose page says the job is gone (also runs at the start of every `run`) |
| `autojob stats` | Counts by status, source, score; recent runs |
| `autojob action <job_id> applied\|dismissed` | Record your decision (the dashboard does this for you) |
| `autojob worker` | Executes dashboard requests (run / docs / abort); runs as a systemd user service |
| `autojob doctor` | Configuration check |

## Configuration

| File | Tracked | Contents |
|---|---|---|
| `.env` | no | API keys, Telegram token |
| `profile/candidate.md` | no | Who you are, what you want, hard constraints — injected into the scoring prompt |
| `profile/resume.tex`, `profile/cover_letter.tex` | no | Your LaTeX templates (`profile.example/` has minimal ones) |
| `config/search.yaml` | yes | Queries, city, thresholds, prefilter rules, expiry limits, model list, per-source settings, company boards, Workday tenants |
| `prompts/*.md` | yes | Scorer / resume / cover letter prompts |

Data lives in `data/autojob.db` (SQLite; jobs are never deleted) and `output/<date>/<company>_<id>/` (PDFs). Both git-ignored.

## Scheduling

`systemd/` holds user units: `autojob.timer` (07:00 daily) and `autojob-worker.service`. `scripts/install.sh` installs them;
on a headless box also run `sudo loginctl enable-linger $USER`. Any cron works too: `autojob run`.

## Design notes

- **Never re-score.** The old version wiped unshortlisted jobs at the start of each run, then re-fetched and re-scored the
  same ~550 postings daily. Now every URL is remembered; a run costs ~100–200 model calls instead of 550+.
- **Docs on demand.** 96% of the resumes generated automatically by the old version were never opened. Automatic generation
  is now limited to top scores (`auto_docs_min_score`); the rest is one click in the dashboard.
- **Budgets everywhere.** Serper credits, YC probes, scrapes and LLM calls are all capped per run in `search.yaml`.
- **Sources are isolated.** One failing source logs an error and the run continues; per-source yield is recorded in
  `source_runs` and shown in the dashboard.
- **Documents are rendered, not written in LaTeX by the model.** Cover letter: the model returns JSON fields for a fixed
  template. Resume: the model only chooses the order of your existing bullets (dropping at most one per section) and writes
  a summary that is rejected if it cites a number or tool that is not already in your resume. Your wording never changes;
  if the page overflows, trailing bullets are dropped without another model call.
- **The review queue only holds live postings.** Shortlisted jobs you have not acted on are retired (status `expired`)
  when the posting is older than `expiry.posted_max_days` or its page returns 404 / "no longer accepting applications".
  Postings already older than `prefilter.max_posted_age_days` when first seen are not even scored.
- **Cheap rules before the model.** Title words, employment type, posting age and a strict location pass
  (`Toronto, Ontario, Canada` is Toronto; `Remote - Houston` is Houston) drop most noise before an LLM call is spent.

See `docs/ARCHITECTURE.md` and `docs/SOURCES.md`.

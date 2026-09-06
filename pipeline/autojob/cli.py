"""Command line interface: ``autojob <command>``."""
from __future__ import annotations

import argparse
import json
import sys
import time

from autojob import db as D
from autojob import sources as S
from autojob.settings import CONFIG_PATH, DB_PATH, PROFILE_DIR, get_settings


def cmd_run(args: argparse.Namespace) -> int:
    from autojob.pipeline import AlreadyRunning, run

    only = [s.strip() for s in args.sources.split(",")] if args.sources else None
    try:
        s = run(get_settings(), dry_run=args.dry_run, only_sources=only,
                no_notify=args.no_notify, max_jobs=args.max_jobs)
    except AlreadyRunning as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps({k: getattr(s, k) for k in ("run_id", "status", "fetched", "new_jobs", "prefiltered", "scored",
                                                  "queued", "skipped", "docs", "errors", "llm_calls")}, indent=2))
    return 0 if s.status in ("done", "aborted") else 1


def cmd_docs(args: argparse.Namespace) -> int:
    from autojob.pipeline import generate_docs_for, setup_logging

    setup_logging()
    D.init_db()
    with D.db() as conn:
        n = generate_docs_for(get_settings(), conn, [int(i) for i in args.job_ids])
        for jid in args.job_ids:
            job = D.get_job(conn, int(jid))
            if job:
                print(f"{jid}: {job['status']} {job.get('output_folder') or ''}")
    return 0 if n == len(args.job_ids) else 1


def cmd_sources(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.action == "list":
        for name in S.SOURCE_NAMES:
            print(f"{'on ' if settings.source_enabled(name) else 'off'}  {name}")
        return 0
    from autojob.pipeline import setup_logging
    setup_logging(verbose=args.verbose)
    names = args.names or S.enabled(settings)
    rc = 0
    for name in names:
        t0 = time.monotonic()
        try:
            jobs = S.load(name).fetch(settings)
        except Exception as e:  # noqa: BLE001
            print(f"{name}: ERROR {type(e).__name__}: {e}")
            rc = 1
            continue
        print(f"{name}: {len(jobs)} jobs in {time.monotonic() - t0:.0f}s")
        for j in jobs[: args.show]:
            print(f"   - {j.title[:60]!r} | {j.company[:28]} | {j.location[:32]} | desc={len(j.description)} | {j.url[:70]}")
    return rc


def cmd_stats(_: argparse.Namespace) -> int:
    D.init_db()
    with D.db() as conn:
        s = D.stats(conn)
    print(f"database: {DB_PATH}")
    print(f"jobs: {s['total']}")
    print("by status:   " + ", ".join(f"{k}={v}" for k, v in sorted(s["by_status"].items())))
    print("by source:   " + ", ".join(f"{k}={v}" for k, v in s["by_source"].items()))
    print("your actions:" + ", ".join(f" {k}={v}" for k, v in s["by_user_action"].items()))
    print("scores:      " + ", ".join(f"{k}:{v}" for k, v in s["score_distribution"].items()))
    print("recent runs:")
    for r in s["last_runs"]:
        print(f"  #{r['id']} {r['started_at'][:16]} {r['status']:8} fetched={r['fetched']} new={r['new_jobs']} "
              f"prefiltered={r['prefiltered']} scored={r['scored']} queued={r['queued']} docs={r['docs']} errors={r['errors']}")
    return 0


def cmd_companies(args: argparse.Namespace) -> int:
    from autojob import ats
    from autojob.pipeline import setup_logging

    setup_logging()
    D.init_db()
    settings = get_settings()
    cfg = settings.source("ats_companies")
    if args.action == "verify":
        dead: list[str] = []
        with D.db() as conn:
            for ats_type in ats.FETCHERS:
                for slug in cfg.get(ats_type, []) or []:
                    try:
                        n = len(ats.fetch_board(ats_type, slug, "", "check"))
                        print(f"ok    {ats_type:16} {slug:28} {n} postings")
                    except Exception as e:  # noqa: BLE001
                        code = getattr(getattr(e, "response", None), "status_code", None)
                        print(f"DEAD  {ats_type:16} {slug:28} {code or type(e).__name__}")
                        dead.append(f"{ats_type}/{slug}")
                    time.sleep(0.15)
            conn.commit()
        if dead:
            print(f"\n{len(dead)} dead slugs — remove them from {CONFIG_PATH}: " + ", ".join(dead))
        return 0
    if args.action == "probe":
        with D.db() as conn:
            for name in args.names:
                slug = name.strip().lower().replace(" ", "-")
                t, url = ats.probe(conn, slug, name)
                print(f"{name:28} → {t or 'none'} {url or ''}")
        return 0
    if args.action == "news":
        return _companies_news(settings)
    return 1


def _companies_news(settings) -> int:
    """Hiring press releases via serper /news (a few credits) → probe the company names found.
    The earliest signal there is: 'opening a Vancouver office, 300 jobs' runs before postings hit boards."""
    import re

    from autojob import ats
    from autojob.db import connect
    from autojob.sources.base import post_json

    key = settings.secrets.serper_api_key
    if not key:
        print("no serper key")
        return 1
    queries = settings.get("discovery.news_queries", [
        'Vancouver office opening hiring', 'Vancouver company expanding jobs', 'BC tech company hiring Vancouver'])
    verb = re.compile(r"^([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*)*?)\s+(?:announces?|opens?|opening|expands?|expanding|"
                      r"to open|to expand|to add|adding|creating|launches?|plans)\b")
    names: list[str] = []
    spent = 0
    for q in queries[:3]:
        try:
            data = post_json("https://google.serper.dev/news", json={"q": q, "num": 20}, headers={"X-API-KEY": key})
            spent += 1
        except Exception as e:  # noqa: BLE001
            print(f"query '{q}' failed: {str(e)[:100]}")
            continue
        for a in data.get("news", []):
            m = verb.match((a.get("title") or "").strip())
            if m and 2 < len(m.group(1)) < 40:
                names.append(m.group(1))
    names = list(dict.fromkeys(names))[:12]
    print(f"{len(names)} company candidates from {len(queries[:3])} news queries:")
    with connect() as conn:
        if spent:  # keep the serper balance badge honest (run-source counter lives in sources/serper.py)
            conn.execute("INSERT INTO meta(key, value) VALUES('serper_credits_used', '0') ON CONFLICT(key) DO NOTHING")
            conn.execute("UPDATE meta SET value = CAST(value AS INTEGER) + ? WHERE key = 'serper_credits_used'", (spent,))
        for name in names:
            slug = re.sub(r"[^a-z0-9]", "", name.lower())
            t, url = ats.probe(conn, slug, name)
            print(f"  {name:32} → {t or 'none':16} {url or ''}")
    print("add hits to sources.ats_companies.<vendor> in search.yaml")
    return 0


def cmd_expire(args: argparse.Namespace) -> int:
    from autojob.expire import expire
    from autojob.pipeline import setup_logging

    setup_logging()
    D.init_db()
    settings = get_settings()
    cfg = settings.get("expiry", {}) or {}
    with D.db() as conn:
        res = expire(
            conn,
            posted_max_days=args.posted_days if args.posted_days is not None else int(cfg.get("posted_max_days", 30)),
            fetched_max_days=args.fetched_days if args.fetched_days is not None else int(cfg.get("fetched_max_days", 45)),
            link_checks=args.links if args.links is not None else int(cfg.get("link_checks_per_run", 0)),
            dry_run=args.dry_run,
        )
        for jid, reason in res["reasons"]:
            job = D.get_job(conn, jid) or {}
            print(f"{'would expire' if args.dry_run else 'expired':12} #{jid} {str(job.get('title'))[:45]:45} "
                  f"{str(job.get('company'))[:22]:22} — {reason}")
    print(f"{res['by_age']} by age, {res['by_link']} by link check ({res['checked']} links checked)"
          + (" [dry run]" if args.dry_run else ""))
    return 0


def cmd_worker(_: argparse.Namespace) -> int:
    from autojob.worker import main as worker_main

    worker_main()
    return 0


def cmd_action(args: argparse.Namespace) -> int:
    D.init_db()
    with D.db() as conn:
        D.set_user_action(conn, int(args.job_id), args.action)
    print("ok")
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    import shutil

    settings = get_settings()
    ok = True

    def check(label: str, good: bool, hint: str = "") -> None:
        nonlocal ok
        ok &= good
        print(f"{'✔' if good else '✘'} {label}{'' if good else '  → ' + hint}")

    check("config/search.yaml", CONFIG_PATH.exists(), f"missing {CONFIG_PATH}")
    check("profile/candidate.md", settings.candidate_profile_path.exists(), "copy profile.example/ to profile/ and edit")
    check("profile/resume.tex", settings.resume_template_path.exists(), "add your LaTeX resume")
    check("profile/cover_letter.tex", settings.cover_letter_template_path.exists(), "add the cover letter template")
    check("LLM_API_KEY", bool(settings.secrets.llm_api_key), "set it in .env")
    check("pdflatex", shutil.which("pdflatex") is not None, "apt install texlive-latex-extra (or TinyTeX)")
    check("pdfinfo", shutil.which("pdfinfo") is not None, "apt install poppler-utils")
    check("Telegram", bool(settings.secrets.telegram_bot_token and settings.secrets.telegram_chat_id), "optional: set TELEGRAM_* in .env")
    for name, has in (("serper", settings.secrets.serper_api_key), ("adzuna", settings.secrets.adzuna_app_id),
                      ("jooble", settings.secrets.jooble_api_key)):
        if settings.source_enabled(name):
            check(f"{name} key", bool(has), f"set it in .env or disable sources.{name} in search.yaml")
    print(f"profile dir: {PROFILE_DIR}\ndatabase:    {DB_PATH}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="autojob", description="Automated job search pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="fetch, score and notify (the daily job)")
    r.add_argument("--dry-run", action="store_true", help="score but generate no documents and send no digest")
    r.add_argument("--sources", help="comma-separated subset of sources")
    r.add_argument("--no-notify", action="store_true", help="skip the Telegram digest")
    r.add_argument("--max-jobs", type=int, help="score at most N jobs (testing)")
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("docs", help="generate resume + cover letter for job id(s)")
    d.add_argument("job_ids", nargs="+")
    d.set_defaults(func=cmd_docs)

    s = sub.add_parser("sources", help="list or test sources")
    s.add_argument("action", choices=["list", "test"])
    s.add_argument("names", nargs="*")
    s.add_argument("--show", type=int, default=5, help="print the first N jobs")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_sources)

    st = sub.add_parser("stats", help="database and run statistics")
    st.set_defaults(func=cmd_stats)

    c = sub.add_parser("companies", help="verify, probe, or news-discover ATS companies")
    c.add_argument("action", choices=["verify", "probe", "news"])
    c.add_argument("names", nargs="*")
    c.set_defaults(func=cmd_companies)

    e = sub.add_parser("expire", help="retire shortlisted postings that are too old or whose page is gone")
    e.add_argument("--dry-run", action="store_true", help="list what would expire, change nothing")
    e.add_argument("--links", type=int, help="how many posting pages to check (default: expiry.link_checks_per_run)")
    e.add_argument("--posted-days", type=int, help="max age by posting date (default: expiry.posted_max_days)")
    e.add_argument("--fetched-days", type=int, help="max age since first seen when no posting date (default: expiry.fetched_max_days)")
    e.set_defaults(func=cmd_expire)

    w = sub.add_parser("worker", help="run the dashboard command worker (systemd service)")
    w.set_defaults(func=cmd_worker)

    a = sub.add_parser("action", help="record your decision on a job")
    a.add_argument("job_id")
    a.add_argument("action", choices=["applied", "dismissed"])
    a.set_defaults(func=cmd_action)

    doc = sub.add_parser("doctor", help="check configuration and dependencies")
    doc.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    sys.exit(args.func(args))

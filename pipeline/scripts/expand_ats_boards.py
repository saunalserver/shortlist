#!/usr/bin/env python3
"""Probe the LastRound ATS directory for boards with Canada-relevant postings.

Dataset: LastRound AI ATS Directory, 9,935 companies -> Greenhouse/Lever/Ashby slugs.
         CC BY 4.0 — datahub.io/lastroundai-hiring-data, DOI 10.6084/m9.figshare.33154145
         (downloaded to data/lastround-ats-directory.csv; refresh ~monthly upstream).
Keeps a board in the ``ats_boards`` table when at least --min-canada of its postings
name Canada/BC; the ats_companies source reads that table (use_discovered_boards: true).

Reruns resume: already-probed slugs are cached in company_ats_cache for 30 days.

Usage: venv/bin/python scripts/expand_ats_boards.py [--limit 200] [--min-canada 1]
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autojob import ats, db as D  # noqa: E402
from autojob.prefilter import CANADA_MARKERS  # noqa: E402
from autojob.settings import get_settings  # noqa: E402

DATASET = Path(__file__).resolve().parent.parent / "data" / "lastround-ats-directory.csv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200, help="boards to probe this run")
    ap.add_argument("--min-canada", type=int, default=1, help="Canada postings required to keep a board")
    args = ap.parse_args()

    settings = get_settings()
    cfg = settings.source("ats_companies")
    known = {s for v in ("greenhouse", "lever", "ashby") for s in cfg.get(v, []) or []}
    with open(DATASET, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("ats_vendor") in ("greenhouse", "lever", "ashby")]

    D.init_db()
    probed = kept = 0
    with D.db() as conn:
        done = conn.execute("SELECT COUNT(*) FROM ats_boards").fetchone()[0]
        for r in rows:
            if probed >= args.limit:
                break
            slug = (r["board_slug"] or "").strip()
            vendor = r["ats_vendor"]
            if not slug or slug in known:
                continue
            cached = D.get_ats_cache(conn, slug)
            if ats.is_fresh(cached):       # probed in the last 30 days — skip, resume works
                continue
            probed += 1
            try:
                jobs = ats.fetch_board(vendor, slug, r["company_name"], "probe")
                canada = sum(1 for j in jobs
                             if any(m in f" {(j.location or '').lower()} " for m in CANADA_MARKERS))
                D.set_ats_cache(conn, slug, r["company_name"], vendor, "")
            except Exception:  # noqa: BLE001
                D.set_ats_cache(conn, slug, r["company_name"], "none", "")
                conn.commit()
                continue
            if canada >= args.min_canada:
                url = {"greenhouse": ats.GREENHOUSE_LIST, "lever": ats.LEVER_LIST,
                       "ashby": ats.ASHBY_LIST}[vendor].format(slug=slug)
                conn.execute("INSERT OR REPLACE INTO ats_boards VALUES (?,?,?,?,?,date('now'))",
                             (vendor, slug, r["company_name"], url, canada))
                kept += 1
                print(f"keep  {vendor:10} {slug:28} {canada:3} Canada jobs  ({r['company_name']})")
            conn.commit()
            time.sleep(0.25)
        total = conn.execute("SELECT COUNT(*) FROM ats_boards").fetchone()[0]
    print(f"\nprobed {probed} boards, kept {kept} new ({done} -> {total} in ats_boards) of {len(rows)} dataset rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

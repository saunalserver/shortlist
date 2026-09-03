#!/usr/bin/env python3
"""One-off migration: copy the dashboard's pipeline_actions (applied / dismissed) from the
Command Center database into jobs.user_action, so the pipeline knows what you decided.

Usage: python scripts/import_tracker_actions.py /path/to/jobsearch.db
Safe to re-run; only fills empty user_action values.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from autojob import db as D  # noqa: E402


def main(tracker_db: str) -> None:
    src = sqlite3.connect(f"file:{tracker_db}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    rows = src.execute("SELECT autojob_id, action, created_at FROM pipeline_actions").fetchall()
    D.init_db()
    updated = missing = 0
    with D.db() as conn:
        for r in rows:
            cur = conn.execute(
                "UPDATE jobs SET user_action = ?, user_action_at = ? WHERE id = ? AND user_action IS NULL",
                (r["action"], r["created_at"], r["autojob_id"]),
            )
            if cur.rowcount:
                updated += 1
            elif not conn.execute("SELECT 1 FROM jobs WHERE id = ?", (r["autojob_id"],)).fetchone():
                missing += 1
    print(f"{len(rows)} actions in tracker → {updated} written, {missing} referenced jobs no longer exist")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/home/saunalserver/projects/shortlist/dashboard/data/jobsearch.db")

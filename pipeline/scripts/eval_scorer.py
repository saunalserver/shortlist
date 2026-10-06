"""Offline evaluation of the job scorer against the owner's real apply/dismiss decisions.

    venv/bin/python scripts/eval_scorer.py build
    venv/bin/python scripts/eval_scorer.py run --version 2 --models config --sample balanced --tag v2-config
    venv/bin/python scripts/eval_scorer.py report --baseline v2-config

Everything lives in data/eval/ (git-ignored: it holds job descriptions and the owner's decisions).
`run` never writes to autojob.db — results go to data/eval/results-<tag>.jsonl and are resumable.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "data" / "eval"
LABELED = EVAL_DIR / "labeled.jsonl"
CURRENT_DB = ROOT / "data" / "autojob.db"
ARCHIVE = Path.home() / "archive" / "projects" / "autojob-2026-09-01"
LEGACY_DB = ARCHIVE / "autojob-before-reset-2026-09-02.db"
TRACKER_DB = ARCHIVE / "tracker-before-reset-2026-09-02.db"

SEED = 20260928
BULK_MINUTE = 20          # a minute holding this many dismissals is a bulk clean-up, not a judgment
MIN_DESC = 300
EASY_NEGATIVES = 30
JOB_COLS = ("id", "url", "title", "company", "location", "description", "snippet", "employment_type",
            "source", "remote", "fit_score", "scorer_model")


# ---------------------------------------------------------------------------- build

def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _record(row: sqlite3.Row | dict, origin: str, label: int) -> dict[str, Any]:
    r = dict(row)
    return {
        "id": f"{origin}:{r['id']}", "origin": origin, "url": r.get("url"), "title": r.get("title") or "",
        "company": r.get("company") or "", "location": r.get("location") or "",
        "description": r.get("description") or "", "snippet": r.get("snippet") or "",
        "employment_type": r.get("employment_type"), "source": r.get("source"), "remote": r.get("remote"),
        "label": label, "old_score": r.get("fit_score"), "old_model": r.get("scorer_model"),
    }


def _select(conn: sqlite3.Connection, where: str, params: tuple = ()) -> list[sqlite3.Row]:
    # `where` is always a constant from this file; values go through params
    return conn.execute(f"SELECT {', '.join(JOB_COLS)} FROM jobs WHERE {where}", params).fetchall()  # noqa: S608


def build_records(current: Path = CURRENT_DB, legacy: Path = LEGACY_DB, tracker: Path = TRACKER_DB,
                  seed: int = SEED) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    cur = _ro(current)

    # positives
    recs += [_record(r, "current_applied", 1) for r in _select(cur, "user_action = 'applied'")]
    leg = _ro(legacy) if legacy.exists() else None
    if leg:
        recs += [_record(r, "legacy_applied", 1)
                 for r in _select(leg, "user_action = 'applied' AND length(description) > ?", (MIN_DESC,))]
    if tracker.exists():
        tr = _ro(tracker)
        urls = [row[0] for row in tr.execute(
            "SELECT posting_url FROM applications WHERE status = 'applied' AND posting_url IS NOT NULL")]
        for url in urls:
            for origin, conn in (("tracker_current", cur), ("tracker_legacy", leg)):
                if conn is None:
                    continue
                hit = _select(conn, "url = ? AND length(description) > ?", (url, MIN_DESC))
                if hit:
                    recs.append(_record(hit[0], origin, 1))
                    break

    # hard negatives: individually dismissed, scored ≥7 (current) / any (legacy)
    bulk = {row[0] for row in cur.execute(
        "SELECT substr(user_action_at, 1, 16) m FROM jobs WHERE user_action = 'dismissed' "
        "GROUP BY m HAVING count(*) >= ?", (BULK_MINUTE,))}
    for r in _select(cur, "user_action = 'dismissed' AND fit_score >= 7"):
        at = cur.execute("SELECT substr(user_action_at, 1, 16) FROM jobs WHERE id = ?", (r["id"],)).fetchone()[0]
        if at not in bulk:
            recs.append(_record(r, "current_dismissed", 0))
    if leg:
        recs += [_record(r, "legacy_dismissed", 0)
                 for r in _select(leg, "user_action = 'dismissed' AND length(description) > ?", (MIN_DESC,))]

    # easy negatives
    easy = _select(cur, "fit_score <= 2 AND fit_score IS NOT NULL AND user_action IS NULL "
                        "AND length(description) > ?", (MIN_DESC,))
    rng = random.Random(seed)
    recs += [_record(r, "easy_negative", 0) for r in rng.sample(list(easy), min(EASY_NEGATIVES, len(easy)))]
    return dedupe(recs)


def _norm(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def dedupe(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """First occurrence wins (positives are added first, so a job both applied and dismissed stays positive)."""
    seen_url: set[str] = set()
    seen_tc: set[tuple[str, str]] = set()
    out = []
    for r in recs:
        url = (r.get("url") or "").strip()
        tc = (_norm(r["title"]), _norm(r["company"]))
        if (url and url in seen_url) or (tc[0] and tc in seen_tc):
            continue
        if url:
            seen_url.add(url)
        seen_tc.add(tc)
        out.append(r)
    return out


def cmd_build(_: argparse.Namespace) -> None:
    recs = build_records()
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with open(LABELED, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(recs)} records → {LABELED.relative_to(ROOT)}")
    for (origin, label), n in sorted(Counter((r["origin"], r["label"]) for r in recs).items()):
        print(f"  {origin:18} label={label}  {n}")
    print(f"  positives={sum(r['label'] for r in recs)}  negatives={sum(1 - r['label'] for r in recs)}")


# ---------------------------------------------------------------------------- run

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def is_hard_negative(r: dict[str, Any]) -> bool:
    return r["label"] == 0 and r["origin"] != "easy_negative"


def sample(recs: list[dict[str, Any]], mode: str, seed: int = SEED) -> list[dict[str, Any]]:
    if mode == "all":
        return recs
    rng = random.Random(seed)
    pos = [r for r in recs if r["label"] == 1]
    hard = [r for r in recs if is_hard_negative(r)]
    easy = [r for r in recs if r["origin"] == "easy_negative"]
    return pos + rng.sample(hard, min(len(pos), len(hard))) + rng.sample(easy, min(10, len(easy)))


def _llm_thread_safe() -> bool:
    import autojob.llm as llm_mod
    src = Path(llm_mod.__file__).read_text(encoding="utf-8")
    return "threading.Lock" in src or "threading.RLock" in src


def cmd_run(args: argparse.Namespace) -> None:
    from autojob.llm import LLM
    from autojob.scorer import Scorer
    from autojob.settings import get_settings

    settings = get_settings()
    recs = sample(load_jsonl(LABELED), args.sample)
    if not recs:
        sys.exit("no labeled records — run `build` first")
    out_path = EVAL_DIR / f"results-{args.tag}.jsonl"
    done = {r["id"] for r in load_jsonl(out_path)}
    todo = [r for r in recs if r["id"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    if args.models == "config":
        models = settings.get("scoring.models", [])
    else:
        models = [{"name": m.strip(), "rpm": 20} for m in args.models.split(",") if m.strip()]
    workers = args.workers
    if workers > 1 and not _llm_thread_safe():
        print("WARNING: llm.py has no lock — shared pacing/model state is not thread-safe; using 1 worker")
        workers = 1
    llm = LLM(settings.secrets.llm_api_key, settings.secrets.llm_base_url, models,
              max_calls=(args.limit * 3 if args.limit else None))
    scorer = Scorer(settings, llm, version=args.version)
    print(f"[{args.tag}] v{args.version} · {len(todo)} to score ({len(done)} already done) · {workers} worker(s)")
    lock = threading.Lock()

    def one(r: dict[str, Any]) -> dict[str, Any]:
        t0 = time.monotonic()
        res, err = None, None
        try:
            res = scorer.score(r)
        except Exception as e:  # noqa: BLE001 — budget or all-models-failed: record and move on
            err = f"{type(e).__name__}: {str(e)[:200]}"
        if res is None and err is None:
            err = "scorer returned None"
        return {
            "id": r["id"], "origin": r["origin"], "label": r["label"], "title": r["title"],
            "company": r["company"], "fit_score": res.get("fit_score") if res else None,
            "skip": res.get("skip") if res else None, "skip_reason": res.get("skip_reason") if res else None,
            "facts": res.get("facts") if res else None, "model": res.get("model") if res else None,
            "seconds": round(time.monotonic() - t0, 1), "error": err,
        }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(one, r) for r in todo]
        for i, f in enumerate(as_completed(futs), 1):
            row = f.result()
            with lock:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
            print(f"  {i}/{len(todo)} {row['fit_score']!s:>4} {'SKIP' if row['skip'] else '    '} "
                  f"label={row['label']} {row['seconds']:>5}s {row['title'][:60]}"
                  + (f"  ERR {row['error']}" if row["error"] else ""))


# ---------------------------------------------------------------------------- report

def auc(pos: list[float], neg: list[float]) -> float | None:
    """P(random positive outranks random negative); ties count 0.5."""
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def kept(row: dict[str, Any], threshold: int) -> bool:
    return row.get("fit_score") is not None and not row.get("skip") and row["fit_score"] >= threshold


def metrics(rows: list[dict[str, Any]], threshold: int) -> dict[str, Any]:
    ok = [r for r in rows if r.get("fit_score") is not None]
    pos = [r for r in ok if r["label"] == 1]
    hard = [r for r in ok if r["label"] == 0 and r.get("origin") != "easy_negative"]
    easy = [r for r in ok if r.get("origin") == "easy_negative"]
    neg = hard + easy
    secs = [r["seconds"] for r in rows if r.get("seconds") is not None]

    def mean(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 2) if xs else None

    return {
        "n": len(rows), "scored": len(ok),
        "errors": len(rows) - len(ok), "error_rate": round((len(rows) - len(ok)) / len(rows), 3) if rows else 0.0,
        "pos": len(pos), "pos_kept": sum(kept(r, threshold) for r in pos),
        "hard": len(hard), "hard_below": sum(not kept(r, threshold) for r in hard),
        "easy": len(easy), "easy_above": sum(kept(r, threshold) for r in easy),
        "auc": auc([r["fit_score"] for r in pos], [r["fit_score"] for r in neg]),
        "mean_pos": mean([r["fit_score"] for r in pos]), "mean_hard": mean([r["fit_score"] for r in hard]),
        "mean_easy": mean([r["fit_score"] for r in easy]), "mean_seconds": mean(secs),
        "dropped_pos": [r for r in pos if not kept(r, threshold)],
    }


def retune_rows(rows: list[dict[str, Any]], weights: dict[str, Any]) -> list[dict[str, Any]]:
    """Re-run compute_v2 over stored facts with new weights — no API calls, no DB access.
    Rows without facts (baseline v1 rows, errors) pass through untouched."""
    from autojob.scorer import compute_v2

    out = []
    for r in rows:
        if isinstance(r.get("facts"), dict):
            res = compute_v2(r["facts"], weights)
            r = {**r, "fit_score": res["fit_score"], "skip": res["skip"], "skip_reason": res["skip_reason"]}
        out.append(r)
    return out


def baseline_rows(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """v1 scores already stored — no API calls. `skip` is unknown for them, so it is treated as False."""
    return [{"id": r["id"], "origin": r["origin"], "label": r["label"], "title": r["title"],
             "company": r["company"], "fit_score": r.get("old_score"), "skip": False, "facts": None,
             "model": r.get("old_model"), "seconds": None, "error": None} for r in recs]


def _pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else f"{a}/0"


def _facts_summary(facts: Any) -> str:
    if not isinstance(facts, dict):
        return ""
    keys = ("role_family", "duties_match", "seniority", "years_required", "employment_type", "work_mode",
            "location_ok", "disqualifiers")
    return ", ".join(f"{k}={facts[k]}" for k in keys if k in facts)


def print_report(tag: str, m: dict[str, Any], threshold: int) -> None:
    print(f"\n=== {tag}  (threshold {threshold})")
    print(f"  n={m['n']} scored={m['scored']} errors={m['errors']} ({m['error_rate']:.1%})")
    print(f"  positives kept        {_pct(m['pos_kept'], m['pos'])}   ← recall that matters")
    print(f"  hard negatives below  {_pct(m['hard_below'], m['hard'])}")
    print(f"  easy negatives above  {_pct(m['easy_above'], m['easy'])}   (should be 0)")
    a = m["auc"]
    speed = f" · {m['mean_seconds']} s/job" if m["mean_seconds"] is not None else ""
    print(f"  AUC {a:.3f}" if a is not None else "  AUC n/a",
          f"· mean score pos={m['mean_pos']} hard={m['mean_hard']} easy={m['mean_easy']}{speed}")
    for r in m["dropped_pos"]:
        print(f"    dropped +: {r['fit_score']} {'SKIP ' if r.get('skip') else ''}{r['title'][:55]} | "
              f"{r['company'][:25]} {_facts_summary(r.get('facts'))}"
              + (f" | {r.get('skip_reason')}" if r.get("skip_reason") else ""))


def cmd_report(args: argparse.Namespace) -> None:
    from autojob.settings import get_settings

    threshold = int(get_settings().get("scoring.min_score_to_queue", 7))
    recs = load_jsonl(LABELED)
    origin = {r["id"]: r["origin"] for r in recs}
    if args.baseline:
        ids = None
        if args.tags:   # compare on the same sample as the first tag
            ids = {r["id"] for r in load_jsonl(EVAL_DIR / f"results-{args.tags[0]}.jsonl")}
        base = [r for r in recs if ids is None or r["id"] in ids]
        print_report("baseline (stored v1 scores)" + (f" on {args.tags[0]} sample" if ids else ""),
                     metrics(baseline_rows(base), threshold), threshold)
    for tag in args.tags:
        rows = load_jsonl(EVAL_DIR / f"results-{tag}.jsonl")
        for r in rows:
            r.setdefault("origin", origin.get(r["id"], ""))
        print_report(tag, metrics(rows, threshold), threshold)


def cmd_retune(args: argparse.Namespace) -> None:
    """Offline weight tuning: re-score a stored results file through compute_v2 with the CURRENT config
    weights (scoring.v2 + the family tiers in scorer.py). Zero API calls — the facts are already in the
    file, so this is the loop for tuning weights against the owner's apply/dismiss labels."""
    from collections import Counter

    from autojob.settings import get_settings

    settings = get_settings()
    weights = settings.get("scoring.v2", {}) or {}
    threshold = args.threshold or int(settings.get("scoring.min_score_to_queue", 7))
    for tag in args.tags:
        rows = retune_rows(load_jsonl(EVAL_DIR / f"results-{tag}.jsonl"), weights)
        m = metrics(rows, threshold)
        print_report(f"{tag} retuned (current config weights, 0 API calls)", m, threshold)
        pos_scores = Counter(r.get("fit_score") for r in rows if r["label"] == 1 and r.get("fit_score") is not None)
        print("  positive scores:", " ".join(f"{s}×{n}" for s, n in sorted(pos_scores.items(), reverse=True)) or "n/a")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="write data/eval/labeled.jsonl from the DBs")
    r = sub.add_parser("run", help="score the labeled set (never writes autojob.db)")
    r.add_argument("--version", type=int, choices=(1, 2), required=True)
    r.add_argument("--models", default="config", help="'config' or a comma list of model ids")
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--sample", choices=("balanced", "all"), default="balanced")
    r.add_argument("--tag", required=True)
    p = sub.add_parser("report", help="metrics per results tag")
    p.add_argument("tags", nargs="*")
    p.add_argument("--baseline", action="store_true", help="also report the stored v1 scores (no API calls)")
    t = sub.add_parser("retune", help="offline: re-run compute_v2 over a stored results file's facts with config weights")
    t.add_argument("tags", nargs="+", default=["v2-off"])
    t.add_argument("--threshold", type=int, default=0, help="override scoring.min_score_to_queue for this report")
    args = ap.parse_args()
    {"build": cmd_build, "run": cmd_run, "report": cmd_report, "retune": cmd_retune}[args.cmd](args)


if __name__ == "__main__":
    main()

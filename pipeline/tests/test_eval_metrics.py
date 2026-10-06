"""Math of scripts/eval_scorer.py (no network, no DB)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "eval_scorer", Path(__file__).resolve().parent.parent / "scripts" / "eval_scorer.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


def test_auc_perfect_inverse_and_ties():
    assert ev.auc([9, 8], [2, 3]) == 1.0
    assert ev.auc([2], [9]) == 0.0
    assert ev.auc([7], [7]) == 0.5
    assert ev.auc([8, 6], [7]) == 0.5
    assert ev.auc([], [1]) is None


def _row(label, score, origin="current_dismissed", skip=False, seconds=1.0):
    return {"id": f"{origin}:{score}:{label}", "label": label, "fit_score": score, "skip": skip,
            "origin": origin, "title": "t", "company": "c", "seconds": seconds}


def test_metrics_counts():
    rows = [
        _row(1, 8, "current_applied"), _row(1, 6, "legacy_applied"), _row(1, 9, "current_applied", skip=True),
        _row(0, 8), _row(0, 5), _row(0, 3, "legacy_dismissed"),
        _row(0, 2, "easy_negative"), _row(0, 7, "easy_negative"),
        {"id": "x", "label": 0, "fit_score": None, "origin": "current_dismissed", "seconds": 2.0},
    ]
    m = ev.metrics(rows, threshold=7)
    assert (m["n"], m["scored"], m["errors"]) == (9, 8, 1)
    assert (m["pos"], m["pos_kept"]) == (3, 1)          # 6 below threshold, 9 skipped
    assert (m["hard"], m["hard_below"]) == (3, 2)
    assert (m["easy"], m["easy_above"]) == (2, 1)
    assert len(m["dropped_pos"]) == 2
    assert m["mean_seconds"] == round(10 / 9, 2)


def test_sample_balanced_is_deterministic():
    recs = ([{"id": f"p{i}", "label": 1, "origin": "current_applied"} for i in range(3)]
            + [{"id": f"h{i}", "label": 0, "origin": "current_dismissed"} for i in range(20)]
            + [{"id": f"e{i}", "label": 0, "origin": "easy_negative"} for i in range(30)])
    a, b = ev.sample(recs, "balanced"), ev.sample(recs, "balanced")
    assert [r["id"] for r in a] == [r["id"] for r in b]
    assert sum(r["label"] for r in a) == 3
    assert sum(1 for r in a if r["origin"] == "current_dismissed") == 3
    assert sum(1 for r in a if r["origin"] == "easy_negative") == 10


def test_dedupe_positive_wins():
    recs = [{"url": "u1", "title": "Ops", "company": "A", "label": 1},
            {"url": "u1", "title": "Ops", "company": "A", "label": 0},
            {"url": "u2", "title": "ops ", "company": "a", "label": 0},
            {"url": "", "title": "Other", "company": "B", "label": 0}]
    out = ev.dedupe(recs)
    assert [r["label"] for r in out] == [1, 0]


def test_retune_rows_recomputes_scores():
    """Offline tuning path: stored facts are re-scored by compute_v2; rows without facts pass through."""
    rows = [
        {"id": "x", "label": 1, "origin": "current_applied", "title": "t", "company": "c", "fit_score": 9,
         "skip": False, "facts": {"role_family": "operations", "duties_match": 3, "seniority": "junior"}},
        {"id": "y", "label": 0, "origin": "current_dismissed", "fit_score": 1, "skip": True, "facts": None},
    ]
    w = {"family_base": {"target": 6, "adjacent": 4, "off": 2}, "duties_match": {0: -3, 1: -1, 2: 0, 3: 1},
         "seniority": {"entry": 1, "junior": 1, "mid": 0, "senior": -3, "lead": -3, "manager": 0,
                       "executive": -5}, "signals_cap": 2}
    out = ev.retune_rows(rows, w)
    assert out[0]["fit_score"] == 8 and out[0]["skip"] is False   # target 6 + d3 1 + junior 1
    assert out[1]["fit_score"] == 1 and out[1]["facts"] is None    # untouched
    assert rows[0]["fit_score"] == 9                               # input rows are not mutated

"""Guards against config edits that silently disable the pipeline (a misplaced block once moved the model list
out of `scoring`, and the next run failed with "no LLM models configured")."""
import yaml

from autojob import sources as S
from autojob.settings import ROOT

CFG = yaml.safe_load((ROOT / "config" / "search.yaml").read_text())


def test_scoring_block_is_intact():
    assert CFG["scoring"]["models"] and all(m.get("name") for m in CFG["scoring"]["models"])
    assert CFG["scoring"]["docs_models"]
    assert int(CFG["scoring"]["min_score_to_queue"]) >= 1   # autodoc threshold removed 2026-09-07 (docs on demand)
    assert int(CFG["scoring"]["max_llm_calls_per_run"]) > 0


def test_expiry_and_prefilter_blocks():
    assert int(CFG["expiry"]["posted_max_days"]) > 0 and int(CFG["expiry"]["fetched_max_days"]) > 0
    assert int(CFG["prefilter"]["max_posted_age_days"]) > 0
    assert "chief of staff" in [p.lower() for p in CFG["prefilter"]["title_allow_phrases"]]


def test_every_configured_source_exists_and_queries_present():
    assert CFG["queries"]
    for name, sub in CFG["sources"].items():
        assert name in S.SOURCE_NAMES, f"unknown source in search.yaml: {name}"
        assert isinstance(sub, dict) and "enabled" in sub, name
    assert CFG["sources"]["workday"]["tenants"]

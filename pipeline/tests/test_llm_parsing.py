import json

import pytest

from autojob.llm import parse_json, strip_wrappers


def test_parse_plain():
    assert parse_json('{"a": 1}') == {"a": 1}


def test_parse_strips_gemma_thought_and_fences():
    raw = "<thought>thinking…\nmore</thought>\n```json\n{\"fit_score\": 7}\n```"
    assert parse_json(raw) == {"fit_score": 7}


def test_parse_list_wrapped():
    assert parse_json('[{"x": 1}]') == {"x": 1}


def test_parse_salvages_prefix_text():
    assert parse_json('Sure! {"ok": true} thanks') == {"ok": True}


def test_parse_rejects_garbage():
    with pytest.raises((ValueError, json.JSONDecodeError)):
        parse_json("no json here")


def test_strip_wrappers_latex():
    tex = "```latex\n\\documentclass{article}\n```"
    assert strip_wrappers(tex) == "\\documentclass{article}"


def test_budget_error_propagates_from_scorer(tmp_path, monkeypatch):
    """The pipeline must stop scoring when the budget is hit instead of marking every remaining job as an error."""
    from autojob.llm import LLM, LLMBudgetExceeded
    from autojob.scorer import Scorer

    class S:
        def prompt(self, name):
            return "{candidate_profile}"

        def candidate_profile(self):
            return "profile"

    llm = LLM("key", "https://example.invalid/v1/", [{"name": "m", "rpm": 1000}], max_calls=0)
    with pytest.raises(LLMBudgetExceeded):
        Scorer(S(), llm).score({"title": "x", "description": "y" * 300})


def _llm_with(responses):
    """LLM whose client returns the queued responses/exceptions, model by model."""
    from autojob.llm import LLM

    llm = LLM("key", "https://example.invalid/v1/", [{"name": "m1", "rpm": 1000}, {"name": "m2", "rpm": 1000}])

    class FakeCompletions:
        def create(self, **kwargs):
            if responses:
                r = responses.pop(0)
                if isinstance(r, Exception):
                    raise r
                return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": r})()})()]})()

    llm.client = type("Client", (), {"chat": type("Chat", (), {"completions": FakeCompletions()})()})()
    return llm


def test_bad_json_falls_back_to_next_model():
    """A model returning garbage JSON must not burn the job: one retry on it, then the next model."""
    llm = _llm_with(["not json at all", "still not json", '{"fit_score": 7}'])
    data = llm.chat_json("sys", "user")
    assert data["fit_score"] == 7
    assert llm.last_model == "m2"


def _rl(msg):
    import httpx
    from openai import RateLimitError

    return RateLimitError(message=msg, response=httpx.Response(429, request=httpx.Request("POST", "x")), body=None)


def test_provider_429_cools_but_does_not_deplete():
    err = _rl('429 {"error":{"message":"Provider returned error","code":429}}')
    llm = _llm_with([err, '{"ok": true}'])
    assert llm.chat_json("s", "u") == {"ok": True}
    m1 = llm.models[0]
    assert not m1.depleted and m1.cooldown_until > 0  # cooled, not dropped


def test_daily_quota_429_depletes():
    err = _rl("Rate limit exceeded: free-models-rate-limit: 1000 requests per day")
    llm = _llm_with([err, '{"ok": true}'])
    assert llm.chat_json("s", "u") == {"ok": True}
    assert llm.models[0].depleted  # dropped for the rest of the run


def test_http_400_drops_model_immediately():
    import httpx
    from openai import APIStatusError

    err = APIStatusError("400 no such model", response=httpx.Response(400, request=httpx.Request("POST", "x")), body=None)
    llm = _llm_with([err, '{"ok": true}'])
    assert llm.chat_json("s", "u") == {"ok": True}
    assert llm.models[0].depleted

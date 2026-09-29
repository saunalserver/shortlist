import json

import pytest

from autojob.llm import parse_json, strip_wrappers


@pytest.fixture(autouse=True)
def _no_account_pacing(monkeypatch):
    """The 3 s account-wide pacer is real-API behaviour; unit tests don't need to wait for it."""
    import autojob.llm as L

    monkeypatch.setattr(L, "ACCOUNT_MIN_INTERVAL", 0.0)


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

        def get(self, key, default=None):
            return default

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


def test_empty_completion_moves_to_next_model_without_retry():
    """An empty answer is not retried on the same model: the next model takes the call at once."""
    llm = _llm_with(["", '{"fit_score": 6}'])
    assert llm.chat_json("s", "u") == {"fit_score": 6}
    assert llm.last_model == "m2"
    assert llm.models[0].failures == 1 and not llm.models[0].depleted


def test_empty_completions_eventually_drop_model():
    from autojob.llm import MAX_CONSECUTIVE_ERRORS

    llm2 = _llm_with(["", '{"ok": 1}'])
    llm2.models[0].failures = MAX_CONSECUTIVE_ERRORS - 1
    assert llm2.chat_json("s", "u") == {"ok": 1}
    assert llm2.models[0].depleted


def test_reasoning_and_max_tokens_are_sent():
    from autojob.llm import LLM

    sent = []

    class FakeCompletions:
        def create(self, **kwargs):
            sent.append(kwargs)
            return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": '{"a": 1}'})()})()]})()

    llm = LLM("key", "https://example.invalid/v1/", [
        {"name": "m1", "rpm": 1000, "reasoning": "low", "max_tokens": 900},
    ])
    llm.client = type("Client", (), {"chat": type("Chat", (), {"completions": FakeCompletions()})()})()
    llm.chat_json("s", "u")
    assert sent[0]["extra_body"] == {"reasoning": {"effort": "low"}} and sent[0]["max_tokens"] == 900
    llm.models[0].reasoning = "off"
    llm.chat_json("s", "u")
    assert sent[1]["extra_body"] == {"reasoning": {"enabled": False}}
    yaml_off = LLM("key", "https://example.invalid/v1/", [{"name": "m", "reasoning": False}])
    assert yaml_off.models[0].extra_body() == {"reasoning": {"enabled": False}}


def test_parallel_calls_count_exactly():
    """Worker threads share one LLM: the call counter and budget stay exact."""
    from concurrent.futures import ThreadPoolExecutor

    llm = _llm_with(['{"x": 1}'] * 40)
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda _: llm.chat_json("s", "u"), range(40)))
    assert len(results) == 40 and llm.calls == 40


# -- free-quota probe (OpenRouter GET /key) ------------------------------------

def _llm_quota(models, reserve, recheck, remaining):
    """LLM with a stubbed quota probe and a client that always answers valid JSON on the first model."""
    from autojob.llm import LLM

    llm = LLM("key", "https://openrouter.invalid/v1/", models,
              free_quota_reserve=reserve, quota_recheck_every=recheck)
    llm._probe_free_remaining = lambda: remaining

    class C:
        def create(self, **kwargs):
            return type("R", (), {"choices": [type("Ch", (), {"message": type("M", (), {"content": '{"ok": 1}'})()})()]})()

    llm.client = type("Client", (), {"chat": type("Chat", (), {"completions": C()})()})()
    return llm


def test_free_quota_probe_benches_free_models():
    """At/below the reserve the :free models are benched and the paid fallback answers."""
    llm = _llm_quota([{"name": "a:free", "rpm": 1000}, {"name": "b:free", "rpm": 1000}, {"name": "paid", "rpm": 1000}],
                     reserve=250, recheck=100, remaining=100)
    assert llm.chat_json("s", "u") == {"ok": 1}
    assert llm.models[0].depleted and llm.models[1].depleted
    assert not llm.models[2].depleted and llm.last_model == "paid"


def test_free_quota_exhausted_with_no_paid_raises_budget():
    from autojob.llm import LLMBudgetExceeded

    llm = _llm_quota([{"name": "a:free", "rpm": 1000}], reserve=250, recheck=100, remaining=0)
    with pytest.raises(LLMBudgetExceeded):
        llm.chat_json("s", "u")


def test_probe_failure_never_breaks_a_run():
    llm = _llm_quota([{"name": "m1", "rpm": 1000}], reserve=250, recheck=100, remaining=None)
    assert llm.chat_json("s", "u") == {"ok": 1}
    assert not llm.models[0].depleted


def test_probe_parses_remaining_from_key_endpoint(monkeypatch):
    import autojob.llm as llm_mod
    from autojob.llm import LLM

    llm = LLM("key", "https://openrouter.ai/api/v1", [{"name": "m", "rpm": 1000}])

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"free_model_daily_requests": {"remaining": 506, "limit": 1000}}}

    monkeypatch.setattr(llm_mod.httpx, "get", lambda *a, **k: R())
    assert llm._probe_free_remaining() == 506


def test_openrouter_free_router_counts_as_free():
    """openrouter/free draws on the free bucket even though its name doesn't end in :free."""
    from autojob.llm import _is_free

    assert _is_free("openrouter/free") and _is_free("a:free") and not _is_free("nvidia/nemotron-3.5-lightning")
    llm = _llm_quota([{"name": "openrouter/free", "rpm": 1000}, {"name": "paid", "rpm": 1000}],
                     reserve=250, recheck=100, remaining=10)
    assert llm.chat_json("s", "u") == {"ok": 1}
    assert llm.models[0].depleted and llm.last_model == "paid"


def test_probe_disabled_when_recheck_is_zero():
    llm = _llm_quota([{"name": "m1", "rpm": 1000}], reserve=250, recheck=0, remaining=0)
    probes = []
    llm._probe_free_remaining = lambda: probes.append(1) or 0
    assert llm.chat_json("s", "u") == {"ok": 1}  # remaining=0 would bench, but the probe never runs
    assert not probes and not llm.models[0].depleted


def test_probe_http_failure_returns_none(monkeypatch):
    import autojob.llm as llm_mod
    from autojob.llm import LLM

    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(llm_mod.httpx, "get", boom)
    llm = LLM("key", "https://openrouter.ai/api/v1", [{"name": "m", "rpm": 1000}])
    assert llm._probe_free_remaining() is None

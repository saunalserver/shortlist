"""Thin LLM client: OpenAI-compatible endpoint, ordered model fallback, per-model pacing,
robust JSON extraction (handles Gemma <thought> blocks, code fences, list-wrapped objects).

Failure policy (OpenRouter free models — shared community capacity, provider-level 429s):
- 503 / timeout / provider-429 ("Provider returned error"): one quick retry, then the model sits out
  ~90 s and the next model takes the call. Cooled models are tried again later in the run.
- 429 account daily quota ("per day" / "free-models"): the model is dropped for the rest of the run;
  when the account itself is capped every model reports it and the run ends gracefully.
- Free-model daily quota is also probed proactively (OpenRouter GET /key): at/below the reserve the ":free"
  models are benched for the rest of the run and the paid fallback takes over (no 429-walking the chain).
- 400/401/402/403/404/422: deterministic request errors (402 = out of credit) — dropped immediately.
- Non-JSON output (json mode): retried once on the same model, then the next model takes the call.
- Empty completion (reasoning models that spend their budget thinking, or a flaky provider): no retry
  on the same model — the next model takes the call at once. Still counts toward the error streak.
- Calls are paced per model; :free models additionally pass an account-wide floor (~20 req/min free tier).

Thread-safe: ``pipeline.score_jobs`` calls ``chat_json`` from several worker threads. Pacing, model
state and the call counter are guarded by locks; the HTTP request itself runs unlocked (in parallel).

Per-model options (``scoring.models`` entries): ``rpm``, ``reasoning`` ("low"/"minimal"/"medium"/"high"
→ OpenRouter ``reasoning.effort``; "off" → ``reasoning.enabled=false``) and ``max_tokens``.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import APIStatusError, APITimeoutError, OpenAI, RateLimitError

logger = logging.getLogger("autojob")

OVERLOAD_COOLDOWN = 90.0     # seconds a model sits out after back-to-back 503s / provider 429s
RATELIMIT_COOLDOWN = 60.0    # seconds after a per-minute 429
MAX_CONSECUTIVE_ERRORS = 6   # hard errors in a row before a model is dropped for the run
DETERMINISTIC_HTTP = (400, 401, 402, 403, 404, 422)  # retrying these can never succeed (402 = out of credit)

# The free tier is ~20 req/min per ACCOUNT (all :free models combined) — every FREE call passes this floor
# (paid variants have no platform cap; see _try_model).
ACCOUNT_MIN_INTERVAL = 3.0
_account_last_call = 0.0
_account_lock = threading.Lock()


def _reserve(last: float, interval: float) -> tuple[float, float]:
    """Next free slot on a pacer: (new last-call time, seconds to sleep before calling)."""
    now = time.monotonic()
    slot = max(now, last + interval)
    return slot, slot - now


def _pace_account() -> None:
    """Reserve the next account-wide slot under the lock, then sleep outside it."""
    global _account_last_call
    with _account_lock:
        _account_last_call, wait = _reserve(_account_last_call, ACCOUNT_MIN_INTERVAL)
    if wait > 0:
        time.sleep(wait)


class LLMBudgetExceeded(RuntimeError):
    pass


class LLMAllModelsFailed(RuntimeError):
    pass


@dataclass
class ModelSpec:
    name: str
    rpm: float = 10.0
    reasoning: str | None = None     # OpenRouter reasoning effort, or "off"
    max_tokens: int | None = None
    _last_call: float = field(default=0.0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    depleted: bool = False
    failures: int = 0
    cooldown_until: float = 0.0

    @property
    def min_interval(self) -> float:
        return 60.0 / self.rpm if self.rpm > 0 else 0.0

    def pace(self) -> None:
        with self._lock:
            self._last_call, wait = _reserve(self._last_call, self.min_interval)
        if wait > 0:
            time.sleep(wait)

    def extra_body(self) -> dict[str, Any] | None:
        if not self.reasoning:
            return None
        r = str(self.reasoning).lower()
        if r in ("off", "false", "disabled"):
            return {"reasoning": {"enabled": False}}
        return {"reasoning": {"effort": r}}

    def available(self) -> bool:
        return not self.depleted and time.monotonic() >= self.cooldown_until

    def cool(self, seconds: float, why: str) -> None:
        with self._lock:
            self.cooldown_until = max(self.cooldown_until, time.monotonic() + seconds)
        logger.warning("%s: %s — cooling down for %.0fs, using the next model", self.name, why, seconds)


def _is_overload(err: Exception) -> bool:
    if isinstance(err, APITimeoutError):
        return True
    status = getattr(err, "status_code", None)
    msg = str(err).lower()
    return status in (502, 503, 504) or "high demand" in msg or "overloaded" in msg or "timed out" in msg


def _is_free(name: str) -> bool:
    """True for anything drawing on the free bucket: ":free" variants AND the ``openrouter/free`` router
    (it routes to free models, so it shares the 1,000/day allowance and the 20 req/min account cap)."""
    return name.endswith(":free") or name == "openrouter/free"


class LLM:
    def __init__(self, api_key: str, base_url: str, models: list[dict[str, Any]], max_calls: int | None = None,
                 free_quota_reserve: int = 0, quota_recheck_every: int = 0):
        if not api_key:
            raise RuntimeError("LLM_API_KEY is not set (see .env.example)")
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=90, max_retries=0)
        # YAML reads an unquoted `reasoning: off` as False — treat that as "off", not as "unset".
        self.models = [ModelSpec(name=m["name"], rpm=float(m.get("rpm", 10)),
                                 reasoning="off" if m.get("reasoning") is False else m.get("reasoning"),
                                 max_tokens=int(m["max_tokens"]) if m.get("max_tokens") else None)
                       for m in models]
        if not self.models:
            raise RuntimeError("no LLM models configured")
        self.max_calls = max_calls
        self.calls = 0
        self._api_key, self._base_url = api_key, base_url
        self._quota_reserve = int(free_quota_reserve)
        self._quota_recheck_every = int(quota_recheck_every)
        self._free_probe_done = False       # one probe attempt even on failure — never re-hammer /key per call
        self._free_probed_calls = 0
        self._lock = threading.Lock()          # guards calls + model state changes
        self._local = threading.local()        # last_model is per thread (workers score in parallel)

    @property
    def last_model(self) -> str | None:
        return getattr(self._local, "last_model", None)

    @last_model.setter
    def last_model(self, value: str | None) -> None:
        self._local.last_model = value

    # -- public -----------------------------------------------------------------
    def chat_json(self, system: str, user: str, temperature: float = 0.2) -> dict[str, Any]:
        raw = self._chat(system, user, temperature, json_mode=True)
        return parse_json(raw)

    def chat_text(self, system: str, user: str, temperature: float = 0.3) -> str:
        return strip_wrappers(self._chat(system, user, temperature, json_mode=False))

    # -- internals ----------------------------------------------------------------
    def _probe_free_remaining(self) -> int | None:
        """Remaining free-model requests today from OpenRouter's /key endpoint (None if unknown)."""
        if "openrouter" not in self._base_url:
            return None
        try:
            r = httpx.get(f"{self._base_url.rstrip('/')}/key",
                          headers={"Authorization": f"Bearer {self._api_key}"}, timeout=10)
            r.raise_for_status()
            return int(r.json()["data"]["free_model_daily_requests"]["remaining"])
        except Exception as e:  # a failed probe must never break a run
            logger.info("free-quota probe failed: %s", str(e)[:120])
            return None

    def _check_free_quota(self) -> None:
        """Probe the free bucket; at/below the reserve bench the free models (paid fallback takes over).
        ``quota_recheck_every: 0`` disables probing entirely, including the first check."""
        with self._lock:
            if not self._quota_recheck_every:
                return
            if self._free_probe_done and self.calls - self._free_probed_calls < self._quota_recheck_every:
                return
            self._free_probe_done = True
            self._free_probed_calls = self.calls
        remaining = self._probe_free_remaining()
        if remaining is None:
            return
        with self._lock:
            if remaining > self._quota_reserve:
                logger.info("OpenRouter free bucket: %d remaining (reserve %d, recheck every %d calls)",
                            remaining, self._quota_reserve, self._quota_recheck_every)
                return
            benched = [s for s in self.models if _is_free(s.name) and not s.depleted]
            for s in benched:
                s.depleted = True
            if benched:
                logger.warning("free bucket at %d ≤ reserve %d — benching %d free model(s) for this run, "
                               "paid fallback takes over", remaining, self._quota_reserve, len(benched))
            if not any(not s.depleted for s in self.models):
                raise LLMBudgetExceeded(f"free quota exhausted ({remaining} left, reserve {self._quota_reserve}) "
                                        "— no non-free model left this run")

    def _chat(self, system: str, user: str, temperature: float, json_mode: bool) -> str:
        with self._lock:
            if self.max_calls is not None and self.calls >= self.max_calls:
                raise LLMBudgetExceeded(f"LLM call budget of {self.max_calls} reached")
        self._check_free_quota()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        errors: list[str] = []
        for round_ in range(2):
            for spec in self.models:
                if not spec.available():
                    continue
                result = self._try_model(spec, messages, temperature, json_mode, errors)
                if result is not None:
                    return result
            # Every model is cooling down or depleted. Wait for the soonest cooldown once, then retry the list.
            with self._lock:
                waits = [spec.cooldown_until - time.monotonic() for spec in self.models if not spec.depleted]
            if round_ == 0 and waits:
                wait = max(0.0, min(waits))
                if wait > 120:
                    break
                logger.warning("all models cooling down — waiting %.0fs", wait)
                time.sleep(wait + 0.5)
        raise LLMAllModelsFailed("; ".join(errors) or "no usable model")

    def _try_model(self, spec: ModelSpec, messages: list[dict[str, str]], temperature: float, json_mode: bool,
                   errors: list[str]) -> str | None:
        """Up to two attempts on one model. Returns the completion, or None to move on to the next model."""
        for attempt in range(2):
            spec.pace()
            if _is_free(spec.name):
                _pace_account()  # the ~20 req/min account cap is a free-tier rule; paid variants have none
            try:
                kwargs: dict[str, Any] = {"model": spec.name, "messages": messages, "temperature": temperature}
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                if spec.max_tokens:
                    kwargs["max_tokens"] = spec.max_tokens
                extra = spec.extra_body()
                if extra:
                    kwargs["extra_body"] = extra
                resp = self.client.chat.completions.create(**kwargs)
                with self._lock:
                    self.calls += 1
                self.last_model = spec.name
                content = (resp.choices[0].message.content or "") if resp.choices else ""
                if not content.strip():
                    # No same-model retry: a reasoning model that came back empty usually does it again,
                    # and the next model answers now instead of after a 5 s sleep.
                    with self._lock:
                        spec.failures += 1
                        drop = spec.failures >= MAX_CONSECUTIVE_ERRORS
                        if drop:
                            spec.depleted = True
                    logger.warning("%s: empty completion — next model takes this call", spec.name)
                    if drop:
                        logger.warning("%s: %d errors in a row — dropping it for this run", spec.name, spec.failures)
                    errors.append(f"{spec.name}: empty completion")
                    return None
                if json_mode:
                    parse_json(content)  # validate here so a JSON-broken model falls back instead of burning the job
                with self._lock:
                    spec.failures = 0
                return content
            except RateLimitError as e:
                msg = str(e)
                low = msg.lower()
                if "per_day" in msg or "per day" in low or "daily" in low or "free-models" in low:
                    with self._lock:
                        spec.depleted = True
                    logger.warning("%s quota exhausted (daily) — dropping it for this run", spec.name)
                    errors.append(f"{spec.name}: daily quota")
                    return None
                if "provider returned error" in low:
                    # upstream free-pool saturation, not our quota — cool it, move on now
                    spec.cool(OVERLOAD_COOLDOWN, "provider saturated (429)")
                    errors.append(f"{spec.name}: provider 429")
                    return None
                if attempt == 0:
                    logger.warning("429 on %s — waiting 15s", spec.name)
                    time.sleep(15)
                    continue
                spec.cool(RATELIMIT_COOLDOWN, "rate limited")
                errors.append(f"{spec.name}: rate limited")
                return None
            except (APITimeoutError, APIStatusError, ValueError) as e:
                if isinstance(e, APIStatusError) and getattr(e, "status_code", None) in DETERMINISTIC_HTTP:
                    with self._lock:
                        spec.depleted = True
                    why = "out of credit — top up OpenRouter" if e.status_code == 402 else "config/provider issue"
                    logger.warning("%s: HTTP %s — dropping it for this run (%s)", spec.name, e.status_code, why)
                    errors.append(f"{spec.name}: http {e.status_code}")
                    return None
                if _is_overload(e):
                    if attempt == 0:
                        time.sleep(3)
                        continue
                    spec.cool(OVERLOAD_COOLDOWN, "overloaded (503/timeout)")
                    errors.append(f"{spec.name}: overloaded")
                    return None
                with self._lock:
                    spec.failures += 1
                    drop = spec.failures >= MAX_CONSECUTIVE_ERRORS
                    if drop:
                        spec.depleted = True
                logger.warning("%s error (attempt %d/2): %s", spec.name, attempt + 1, str(e)[:160])
                if drop:
                    logger.warning("%s: %d errors in a row — dropping it for this run", spec.name, spec.failures)
                    errors.append(f"{spec.name}: repeated errors")
                    return None
                if attempt == 0:
                    time.sleep(5)
                    continue
                errors.append(f"{spec.name}: {str(e)[:80]}")
                return None
        return None


_THOUGHT = re.compile(r"<thought>.*?</thought>\s*", re.S)
_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n?(.*?)\n?```\s*$", re.S)


def strip_wrappers(text: str) -> str:
    text = _THOUGHT.sub("", text or "").strip()
    m = _FENCE.match(text)
    if m:
        text = m.group(1).strip()
    return text


def parse_json(text: str) -> dict[str, Any]:
    cleaned = strip_wrappers(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Salvage the first {...} block.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            raise
        data = json.loads(cleaned[start : end + 1])
    if isinstance(data, list):
        data = next((d for d in data if isinstance(d, dict)), {})
    if not isinstance(data, dict):
        raise ValueError("LLM did not return a JSON object")
    return data

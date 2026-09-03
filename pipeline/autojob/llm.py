"""Thin LLM client: OpenAI-compatible endpoint, ordered model fallback, per-model pacing,
robust JSON extraction (handles Gemma <thought> blocks, code fences, list-wrapped objects).

Failure policy (OpenRouter free models — shared community capacity, provider-level 429s):
- 503 / timeout / provider-429 ("Provider returned error"): one quick retry, then the model sits out
  ~90 s and the next model takes the call. Cooled models are tried again later in the run.
- 429 account daily quota ("per day" / "free-models"): the model is dropped for the rest of the run;
  when the account itself is capped every model reports it and the run ends gracefully.
- 400/401/403/404/422: deterministic request errors — the model is dropped immediately.
- Non-JSON output (json mode): retried once on the same model, then the next model takes the call.
- Calls are paced per model AND account-wide (~20 req/min on the free tier, all models combined).
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from openai import APIStatusError, APITimeoutError, OpenAI, RateLimitError

logger = logging.getLogger("autojob")

OVERLOAD_COOLDOWN = 90.0     # seconds a model sits out after back-to-back 503s / provider 429s
RATELIMIT_COOLDOWN = 60.0    # seconds after a per-minute 429
MAX_CONSECUTIVE_ERRORS = 6   # hard errors in a row before a model is dropped for the run
DETERMINISTIC_HTTP = (400, 401, 403, 404, 422)  # retrying these can never succeed

# Free tier is ~20 req/min per ACCOUNT (all free models combined) — every call passes this floor.
ACCOUNT_MIN_INTERVAL = 3.0
_account_last_call = 0.0


def _pace_account() -> None:
    global _account_last_call
    wait = ACCOUNT_MIN_INTERVAL - (time.monotonic() - _account_last_call)
    if wait > 0:
        time.sleep(wait)
    _account_last_call = time.monotonic()


class LLMBudgetExceeded(RuntimeError):
    pass


class LLMAllModelsFailed(RuntimeError):
    pass


@dataclass
class ModelSpec:
    name: str
    rpm: float = 10.0
    _last_call: float = field(default=0.0, repr=False)
    depleted: bool = False
    failures: int = 0
    cooldown_until: float = 0.0

    @property
    def min_interval(self) -> float:
        return 60.0 / self.rpm if self.rpm > 0 else 0.0

    def pace(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def available(self) -> bool:
        return not self.depleted and time.monotonic() >= self.cooldown_until

    def cool(self, seconds: float, why: str) -> None:
        self.cooldown_until = time.monotonic() + seconds
        logger.warning("%s: %s — cooling down for %.0fs, using the next model", self.name, why, seconds)


def _is_overload(err: Exception) -> bool:
    if isinstance(err, APITimeoutError):
        return True
    status = getattr(err, "status_code", None)
    msg = str(err).lower()
    return status in (502, 503, 504) or "high demand" in msg or "overloaded" in msg or "timed out" in msg


class LLM:
    def __init__(self, api_key: str, base_url: str, models: list[dict[str, Any]], max_calls: int | None = None):
        if not api_key:
            raise RuntimeError("LLM_API_KEY is not set (see .env.example)")
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=90, max_retries=0)
        self.models = [ModelSpec(name=m["name"], rpm=float(m.get("rpm", 10))) for m in models]
        if not self.models:
            raise RuntimeError("no LLM models configured")
        self.max_calls = max_calls
        self.calls = 0
        self.last_model: str | None = None

    # -- public -----------------------------------------------------------------
    def chat_json(self, system: str, user: str, temperature: float = 0.2) -> dict[str, Any]:
        raw = self._chat(system, user, temperature, json_mode=True)
        return parse_json(raw)

    def chat_text(self, system: str, user: str, temperature: float = 0.3) -> str:
        return strip_wrappers(self._chat(system, user, temperature, json_mode=False))

    # -- internals ----------------------------------------------------------------
    def _chat(self, system: str, user: str, temperature: float, json_mode: bool) -> str:
        if self.max_calls is not None and self.calls >= self.max_calls:
            raise LLMBudgetExceeded(f"LLM call budget of {self.max_calls} reached")
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
            _pace_account()
            try:
                kwargs: dict[str, Any] = {"model": spec.name, "messages": messages, "temperature": temperature}
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                resp = self.client.chat.completions.create(**kwargs)
                self.calls += 1
                self.last_model = spec.name
                content = (resp.choices[0].message.content or "") if resp.choices else ""
                if not content.strip():
                    raise ValueError("empty completion")
                if json_mode:
                    parse_json(content)  # validate here so a JSON-broken model falls back instead of burning the job
                spec.failures = 0
                return content
            except RateLimitError as e:
                msg = str(e)
                low = msg.lower()
                if "per_day" in msg or "per day" in low or "daily" in low or "free-models" in low:
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
                    spec.depleted = True
                    logger.warning("%s: HTTP %s — dropping it for this run (config/provider issue)", spec.name,
                                   e.status_code)
                    errors.append(f"{spec.name}: http {e.status_code}")
                    return None
                if _is_overload(e):
                    if attempt == 0:
                        time.sleep(3)
                        continue
                    spec.cool(OVERLOAD_COOLDOWN, "overloaded (503/timeout)")
                    errors.append(f"{spec.name}: overloaded")
                    return None
                spec.failures += 1
                logger.warning("%s error (attempt %d/2): %s", spec.name, attempt + 1, str(e)[:160])
                if spec.failures >= MAX_CONSECUTIVE_ERRORS:
                    spec.depleted = True
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

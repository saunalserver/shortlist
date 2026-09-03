"""Shared HTTP helpers for sources."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger("autojob")

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 autojob/2.0"

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.8"})
        _session = s
    return _session


def get_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None,
             timeout: int = 20, retries: int = 2, backoff: float = 2.0) -> Any:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = session().get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 429 and attempt < retries:
                time.sleep(backoff * (attempt + 1) * 2)
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    assert last is not None
    raise last


def get_text(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None,
             timeout: int = 20) -> str:
    resp = session().get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def post_json(url: str, *, json: Any, headers: dict[str, str] | None = None, timeout: int = 20) -> Any:
    resp = session().post(url, json=json, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def title_matches(title: str, keywords: list[str]) -> bool:
    t = (title or "").lower()
    return any(k.lower() in t for k in keywords)

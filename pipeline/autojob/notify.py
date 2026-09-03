"""Telegram digest — one message per run (chunked only if it exceeds Telegram's limit)."""
from __future__ import annotations

import html
import logging
import os
import time
from typing import Any

import requests

from autojob.settings import Settings

logger = logging.getLogger("autojob")
MAX_LEN = 4000
TOP_N = 15


def _send(settings: Settings, text: str) -> bool:
    tok, chat = settings.secrets.telegram_bot_token, settings.secrets.telegram_chat_id
    if not (tok and chat):
        logger.info("telegram not configured — digest:\n%s", text)
        return False
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    for chunk in _chunks(text):
        for _attempt in range(4):
            try:
                r = requests.post(url, json={"chat_id": chat, "text": chunk, "parse_mode": "HTML",
                                             "disable_web_page_preview": True}, timeout=20)
            except requests.RequestException as e:
                logger.warning("telegram send failed: %s", e)
                time.sleep(3)
                continue
            if r.status_code == 429:
                wait = int((r.json().get("parameters") or {}).get("retry_after", 5)) + 1
                time.sleep(wait)
                continue
            if r.status_code != 200:
                logger.warning("telegram error %s: %s", r.status_code, r.text[:200])
            break
    logger.info("telegram: sent %d chars in %d message(s)", len(text), len(_chunks(text)))
    return True


def _chunks(text: str) -> list[str]:
    out: list[str] = []
    while len(text) > MAX_LEN:
        cut = text.rfind("\n\n", 0, MAX_LEN)
        cut = cut if cut > 0 else text.rfind("\n", 0, MAX_LEN)
        cut = cut if cut > 0 else MAX_LEN
        out.append(text[:cut])
        text = text[cut:].lstrip("\n")
    out.append(text)
    return out


def _e(s: Any) -> str:
    return html.escape(str(s or ""), quote=False)


def send_digest(settings: Settings, run: dict[str, Any], queued: list[dict[str, Any]]) -> None:
    date = (run.get("started_at") or "")[:10]
    lines = [f"<b>Autojob — {date}</b>"]
    lines.append(
        f"{run.get('fetched', 0)} fetched · {run.get('new_jobs', 0)} new · {run.get('prefiltered', 0)} filtered · "
        f"{run.get('scored', 0)} scored → <b>{len(queued)} worth a look</b>"
        + (f" · {run['errors']} errors" if run.get("errors") else "")
        + (f" · {run['expired']} old postings retired" if run.get("expired") else "")
    )
    if not queued:
        lines.append("\nNothing cleared the bar today.")
    else:
        lines.append("")
        for j in queued[:TOP_N]:
            score = j.get("fit_score")
            flag = "🔥" if (score or 0) >= 8 else "✅"
            docs = " 📄" if j.get("status") == "docs_generated" else ""
            loc = f" · {_e(j['location'])[:40]}" if j.get("location") else ""
            lines.append(f"{flag} <b>{score}/10</b> · <a href=\"{_e(j.get('url'))}\">{_e(j.get('title'))}</a>{docs}")
            lines.append(f"    {_e(j.get('company'))}{loc} · <i>{_e(j.get('source'))}</i>")
            if j.get("fit_reasoning"):
                lines.append(f"    {_e(j['fit_reasoning'])[:220]}")
            lines.append("")
        if len(queued) > TOP_N:
            lines.append(f"…and {len(queued) - TOP_N} more in the dashboard.")
    dash = os.getenv("DASHBOARD_URL") or settings.get("profile.dashboard_url")
    if dash:
        lines.append(f"\n<a href=\"{_e(dash)}\">Open the review queue</a>")
    _send(settings, "\n".join(lines))


def send_alert(settings: Settings, message: str) -> None:
    _send(settings, f"<b>Autojob alert</b>\n\n{_e(message)[:3000]}")

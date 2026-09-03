"""Cheap, high-precision rejection rules applied before any LLM call.

Every rule must be *obviously* right for the candidate's target roles. Anything
debatable is left for the scorer. Returns a short reason string, or None to keep.

Location logic (``prefilter.location`` in search.yaml), in order:
1. A named non-local Canadian city with nothing saying "remote" → drop, even if the string
   also says "Canada" ("Toronto, Ontario, Canada" is Toronto, not Canada-wide).
2. US-only markers, US states or US cities without any Canadian place name → drop. This now
   applies to remote jobs too ("Remote - Houston", "Chicago, IL, Flexible / Remote").
3. A foreign country/region without a Canadian or global keyword → drop ("Remote - EMEA").
Empty locations always pass (the LLM judges from the description).
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

_US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me",
    "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa",
    "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
}
_CA_PROVINCES = {"bc", "on", "qc", "ab", "mb", "sk", "ns", "nb", "nl", "pe", "yt", "nt", "nu"}
_US_STATE_NAMES = (
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida",
    "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio", "oklahoma",
    "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah",
    "vermont", "virginia", "washington, dc", "west virginia", "wisconsin", "wyoming", "united states", "usa",
)
# Markers that a "remote" role is actually US-only. Shared with the company-board sources.
US_ONLY_MARKERS = (
    "us only", "u.s. only", "us-based", "u.s. based", "us based", "must reside in the us", "authorized to work in the us",
    "us-remote", "us remote", "remote - us", "remote (us)", "remote, us", "remote us", "remote in us", "remote in the us",
    "remote-us", "remote (usa)", "remote usa", "usa remote", "united states", " usa", "u.s.", "(us)", "us-",
)
# Any of these means the posting is (or includes) Canada / the candidate's area → never dropped for location.
CANADA_MARKERS = ("canada", "canadian", "vancouver", "burnaby", "richmond", "surrey", "coquitlam", "new westminster",
                  "langley", "british columbia", ", bc", " bc ", " bc,", " bc)")
# The candidate's commute area — a multi-city posting that names one of these is kept even if it names Toronto too.
LOCAL_MARKERS = ("vancouver", "burnaby", "richmond", "surrey", "coquitlam", "new westminster", "langley", "delta",
                 "port moody", "maple ridge", "white rock", "lower mainland", "metro vancouver", "greater vancouver")
GLOBAL_MARKERS = ("worldwide", "anywhere", "global", "americas", "north america", "international")
REMOTE_MARKERS = ("remote", "anywhere", "worldwide", "work from home", "wfh", "télétravail", "distributed")


@lru_cache(maxsize=8)
def _word_regex(words: tuple[str, ...]) -> re.Pattern[str]:
    """Whole-word match; a trailing plural (s/es) counts too, so "driver" also catches "Drivers"."""
    escaped = sorted((re.escape(w) for w in words), key=len, reverse=True)
    return re.compile(r"(?<![\w-])(?:" + "|".join(escaped) + r")(?:es|s)?(?![\w-])", re.I)


def _has_word(text: str, words: tuple[str, ...]) -> str | None:
    if not words:
        return None
    m = _word_regex(words).search(text)
    return m.group(0).lower() if m else None


def location_reason(location: str, loc_cfg: dict[str, Any], remote: bool | None = None) -> str | None:
    """Why a location rules the job out, or None. ``remote`` is the source's own flag."""
    loc = (location or "").lower().strip()
    if not loc:
        return None
    padded = f" {loc} "
    canada = any(k in padded for k in CANADA_MARKERS)
    local = any(k in padded for k in LOCAL_MARKERS)
    says_remote = remote is True or any(k in padded for k in REMOTE_MARKERS)
    global_ok = any(k in padded for k in GLOBAL_MARKERS)

    # 1. Another Canadian city, on-site (no remote wording) → drop, unless the posting also names our area.
    if not says_remote and not local:
        for city in loc_cfg.get("deny_cities", []) or []:
            if city.lower() in loc:
                return f"location: {city}"

    # 2. United States, unless Canada is named as well.
    if loc_cfg.get("deny_us", True) and not canada:
        if any(p in padded for p in US_ONLY_MARKERS):
            return "location: US only"
        if any(re.search(rf"\b{re.escape(n)}\b", loc) for n in _US_STATE_NAMES):
            return "location: United States"
        city = _has_word(loc, tuple(loc_cfg.get("deny_us_cities", []) or []))
        if city:
            return f"location: {city} (US)"
        m = re.search(r",\s*([a-z]{2})(?:\s+\d{5})?\s*$", loc)   # "City, ST" or "City, ST 12345"
        if m and m.group(1) in _US_STATES and m.group(1) not in _CA_PROVINCES:
            return "location: United States"

    # 3. Pinned to another country/region.
    if not canada and not global_ok:
        country = _has_word(loc, tuple(loc_cfg.get("deny_countries", []) or []))
        if country:
            return f"location: {country}"
    return None


def prefilter_reason(job: dict[str, Any], cfg: dict[str, Any]) -> str | None:
    """Return why a job should be dropped without scoring, or None if it should be scored."""
    title = (job.get("title") or "").strip()
    if len(title) < 4:
        return "title: empty"

    lower_title = title.lower()
    protected = any(p.lower() in lower_title for p in cfg.get("title_allow_phrases", []) or [])
    if not protected:
        word = _has_word(title, tuple(cfg.get("title_exclude_words", []) or []))
        if word:
            return f"title: {word}"
        for phrase in cfg.get("title_exclude_phrases", []) or []:
            if phrase.lower() in lower_title:
                return f"title: {phrase}"

    emp = (job.get("employment_type") or "").lower()
    for bad in cfg.get("employment_type_exclude", []) or []:
        if bad.lower() in emp:
            return f"employment type: {bad}"

    max_age = int(cfg.get("max_posted_age_days", 0) or 0)
    if max_age:
        age = posted_age_days(job.get("posted_at"))
        if age is not None and age > max_age:
            return f"posted: {str(job.get('posted_at'))[:10]} ({age} days ago)"

    return location_reason(job.get("location") or "", cfg.get("location", {}) or {}, job.get("remote"))


def posted_age_days(posted_at: str | None, today: datetime | None = None) -> int | None:
    posted = (posted_at or "")[:10]
    if not posted:
        return None
    try:
        dt = datetime.fromisoformat(posted).replace(tzinfo=UTC)
    except ValueError:
        return None
    return ((today or datetime.now(UTC)) - dt).days

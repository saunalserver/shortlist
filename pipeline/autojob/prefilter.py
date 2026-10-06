"""Cheap, high-precision rejection rules applied before any LLM call.

Every rule must be *obviously* right for the candidate's target roles. Anything
debatable is left for the scorer. Returns a short reason string, or None to keep.

Location logic (``prefilter.location`` in search.yaml), in order:
1. A named non-local Canadian city with nothing saying "remote" → drop, even if the string
   also says "Canada" ("Toronto, Ontario, Canada" is Toronto, not Canada-wide).
2. US-only markers, US states or US cities without any Canadian place name → drop. This now
   applies to remote jobs too ("Remote - Houston", "Chicago, IL, Flexible / Remote").
3. A foreign country/region without a Canadian or global keyword → drop ("Remote - EMEA"), except a
   remote job naming only European countries/cities in ``remote_ok_countries`` ("Remote — Paris, France").
Empty locations always pass (the LLM judges from the description).
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from autojob.normalize import company_key

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
# 2026-10-06 (owner): US-remote is in policy WHEN DOABLE FROM CANADA. These state an actual residency /
# work-authorization restriction, so they stay hard kills even for remote jobs; everything else US only
# kills on-site/hybrid postings — a remote US-based job passes through to the scorer, which DQs residency pins.
US_RESIDENCY_MARKERS = (
    "us only", "u.s. only", "must reside in the us", "must reside in the usa", "us residents only",
    "authorized to work in the us", "work authorization for the us", "us citizens only",
)
# Any of these means the posting is (or includes) Canada / the candidate's area → never dropped for location.
CANADA_MARKERS = ("canada", "canadian", "vancouver", "burnaby", "richmond", "surrey", "coquitlam", "new westminster",
                  "langley", "british columbia", ", bc", " bc ", " bc,", " bc)")
# The candidate's commute area — a multi-city posting that names one of these is kept even if it names Toronto too.
LOCAL_MARKERS = ("vancouver", "burnaby", "richmond", "surrey", "coquitlam", "new westminster", "langley", "delta",
                 "port moody", "maple ridge", "white rock", "lower mainland", "metro vancouver", "greater vancouver")
def is_local(location: str) -> bool:
    """Vancouver-area place named? ("Richmond Hill, ON" is not Richmond, BC.)"""
    loc = (location or "").lower().replace("richmond hill", "")
    return any(k in loc for k in LOCAL_MARKERS)


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


def _all_words(text: str, words: tuple[str, ...]) -> list[str]:
    """Every whole-word hit, lower-cased with any plural suffix stripped back to the listed word."""
    if not words:
        return []
    listed = {w.lower() for w in words}
    out = []
    for m in _word_regex(words).finditer(text):
        w = m.group(0).lower()
        for cand in (w, w[:-1], w[:-2]):
            if cand in listed:
                out.append(cand)
                break
    return out


def location_reason(location: str, loc_cfg: dict[str, Any], remote: bool | None = None) -> str | None:
    """Why a location rules the job out, or None. ``remote`` is the source's own flag."""
    loc = (location or "").lower().strip()
    if not loc:
        return None
    padded = f" {loc} "
    canada = any(k in padded for k in CANADA_MARKERS)
    # "Remote, CA" — boards' Canada remote_only pass writes exactly this — is remote-Canada (province-style
    # CA), not California: 281 such rows were prefiltered as US, 0 ever scored. Only when "remote" is the
    # place being qualified; "San Francisco, CA" and other real US cities still die in rule 2.
    canada = canada or bool(re.fullmatch(r"remote[\s,\u2013-]+ca", loc))
    local = is_local(padded)
    says_remote = bool(remote) or any(k in padded for k in REMOTE_MARKERS)   # SQLite hands us int 1, not True
    global_ok = any(k in padded for k in GLOBAL_MARKERS)
    # hybrid/partial wording = must sometimes be on site somewhere — not remote-doable from Vancouver
    partial = re.search(r"hybrid|hybride|partiel|partial|occasional|ponctuel", loc)

    # 1. Another Canadian city, on-site (no remote wording) → drop, unless the posting also names our area.
    if not says_remote and not local:
        for city in loc_cfg.get("deny_cities", []) or []:
            if city.lower() in loc:
                return f"location: {city}"

    # 2. United States. 2026-10-06 (owner): US-remote is acceptable when doable from Canada — a remote
    #    US-based job passes to the scorer (which hard-DQs explicit US-residency pins); on-site/hybrid US
    #    and explicit residency restrictions still die here.
    if loc_cfg.get("deny_us", True) and not canada:
        if any(p in padded for p in US_RESIDENCY_MARKERS):
            return "location: US only"
        if not (says_remote and not partial):
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

    # 3. Pinned to another country/region. A *remote* job naming only European countries/cities is kept
    #    (remote_ok_countries): a bare "Remote — Paris, France" is usually the office, not a residency rule,
    #    and the user wants undecidable remote jobs scored. Regions ("Remote - EMEA", "Europe") stay dropped:
    #    they are the residency rule. Explicit country lists are enforced at source (Himalayas, RR, Getro…).
    if not canada and not global_ok:
        hits = _all_words(loc, tuple(loc_cfg.get("deny_countries", []) or []))
        if hits:
            ok = {c.lower() for c in loc_cfg.get("remote_ok_countries", []) or []}
            if says_remote and not partial and all(h in ok for h in hits):
                return None
            return f"location: {hits[0]}"
    return None


def prefilter_reason(job: dict[str, Any], cfg: dict[str, Any],
                     company_blocklist: set[str] | None = None) -> str | None:
    """Return why a job should be dropped without scoring, or None if it should be scored."""
    title = (job.get("title") or "").strip()
    if len(title) < 4:
        return "title: empty"

    if company_blocklist and company_key(job.get("company")) in company_blocklist:
        return "company_blocklist"

    # 2026-10-06 (owner): hard-block edu/gov/nonprofit employers — 0/18 applies vs 17/290 deliberate
    # dismissals (report 01 §2.5; validated against all 18 applied companies: zero matches). Substring
    # match on the company name; the word list lives in search.yaml (employer_block_words) for tuning.
    company = (job.get("company") or "").lower()
    for w in cfg.get("employer_block_words", []) or []:
        if w and w in company:
            return f"employer: {w}"

    lower_title = title.lower()
    protected = any(p.lower() in lower_title for p in cfg.get("title_allow_phrases", []) or [])
    if not protected:
        exclude = tuple(cfg.get("title_exclude_words", []) or [])
        # Supply-chain carve-out: planner/buyer/scheduler are excluded words, but paired with a
        # supply-chain function word (search.yaml title_sc_*) they are the 09-06 target family —
        # only those words stop being exclusions; senior/director/contract… still kill.
        sc_words = {w.lower() for w in cfg.get("title_sc_words", []) or []}
        if sc_words and _has_word(title, tuple(cfg.get("title_sc_markers", []) or [])):
            exclude = tuple(w for w in exclude if w.lower() not in sc_words)
        word = _has_word(title, exclude)
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

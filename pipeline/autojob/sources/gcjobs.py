"""GC Jobs — Government of Canada postings open to the public (federal departments, Crown corps and
agencies such as CMHC, Bank of Canada, OSFI). No key, but a session is required.

Flow: open the job-search page (sets JSESSIONID) → fetch the results fragment
(``isSecondPartOfPage=1``) → page through ``requestedPage=N`` (20 postings/page, ~21 pages). Each result
has title, closing date, organization, location, language requirement and salary — no posting date,
so expiry counts from first seen. The site's own title filter does not apply, so everything is
crawled and filtered here: Lower Mainland / "Various Locations" / telework postings whose title matches
``title_keywords``.

Kept postings get their detail page fetched in the same session (the page only works with a session
cookie). Many organizations advertise on their own site; GC Jobs then shows a "You will leave the GC
Jobs Web site" page and we keep the employer's URL instead, which the scraper can fetch later.

Bilingual requirements are a strength for this candidate — they go into the snippet. Core public
service postings give preference to Canadian citizens (PSEA s.39); separate employers listed in
``non_psea_employers`` do not. The snippet says which applies so the scorer can weigh it.
"""
from __future__ import annotations

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from autojob.models import RawJob
from autojob.normalize import canonical_url, snippet_of, truncate
from autojob.settings import Settings
from autojob.sources.base import USER_AGENT, title_matches

NAME = "gcjobs"
logger = logging.getLogger("autojob")
HOST = "https://emploisfp-psjobs.cfp-psc.gc.ca"
SEARCH = HOST + "/psrs-srfp/applicant/page2440"

DEFAULT_LOCATIONS = ["vancouver", "burnaby", "surrey", "richmond (british", "new westminster", "coquitlam", "delta (british",
                     "langley", "various locations", "telework", "remote", "virtual"]
DEFAULT_NON_PSEA = ["bank of canada", "canada mortgage and housing", "office of the superintendent of financial",
                    "canadian commercial corporation", "canada revenue agency", "national research council",
                    "parks canada", "library of parliament", "canadian food inspection", "export development canada",
                    "business development bank", "canada post", "house of commons", "senate of canada"]


_PROVINCES = ("British Columbia|Alberta|Saskatchewan|Manitoba|Ontario|Quebec|Québec|New Brunswick|Nova Scotia|"
              "Prince Edward Island|Newfoundland and Labrador|Yukon|Northwest Territories|Nunavut")
_LOCATION_LINE = re.compile(rf"\((?:{_PROVINCES})\)|^various locations|telework|remote|^virtual|outside canada", re.I)


def parse_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []
    for li in soup.select("li.searchResult"):
        a = li.find("a", href=re.compile(r"page1800\?poster=\d+"))
        if not a:
            continue
        cells = li.select(".tableCell")
        left = [s.strip() for s in cells[0].get_text("\n", strip=True).split("\n") if s.strip()] if cells else []
        right = [s.strip() for s in cells[1].get_text("\n", strip=True).split("\n") if s.strip()] if len(cells) > 1 else []
        closing = next((x.split(":", 1)[1].strip() for x in left if x.lower().startswith("closing date")), None)
        rest = [re.sub(r"\s+", " ", x) for x in left if not x.lower().startswith("closing date")]
        loc_lines = [x for x in rest if _LOCATION_LINE.search(x)]
        org = " ".join(x for x in rest if x not in loc_lines).strip()
        location = "; ".join(loc_lines)
        rows.append({
            "poster": re.search(r"poster=(\d+)", a["href"]).group(1),
            "title": re.sub(r"\s+", " ", a.get_text(" ", strip=True)),
            "organization": re.sub(r"\s+", " ", org),
            "location": location,
            "closing": closing,
            "language": right[0] if right else "",
            "salary": re.sub(r"\s*\(.*$", "", right[1])[:80] if len(right) > 1 else "",
        })
    return rows


def total_pages(html: str) -> int:
    m = re.search(r"</a>\s*of\s*(\d+)", html)
    return int(m.group(1)) if m else 1


def parse_detail(html: str) -> tuple[str | None, str]:
    """→ (external employer URL or None, description text)."""
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup
    text = main.get_text("\n", strip=True)
    if "You will leave the" in text[:200]:
        for a in main.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "cfp-psc.gc.ca" not in href:
                return href, ""
        return None, ""
    for marker in ("Date modified:",):
        i = text.find(marker)
        if i > 0:
            text = text[:i]
    return None, re.sub(r"[ \t]+", " ", text).strip()


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def fetch(settings: Settings) -> list[RawJob]:
    cfg = settings.source(NAME)
    keywords = list(cfg.get("title_keywords") or [])
    exclude = [w.lower() for w in cfg.get("title_exclude", []) or []]
    locs = [x.lower() for x in cfg.get("locations") or DEFAULT_LOCATIONS]
    non_psea = [x.lower() for x in cfg.get("non_psea_employers") or DEFAULT_NON_PSEA]
    bad_orgs = [x.lower() for x in cfg.get("exclude_employers", []) or []]
    max_pages = int(cfg.get("max_pages", 30))
    max_details = int(cfg.get("max_details_per_run", 40))
    delay = float(cfg.get("delay_s", 0.8))

    rows: list[dict] = []
    first = None
    for attempt in (1, 2):   # the site intermittently answers "Lost Connection" — one retry on a fresh session
        s = _session()
        try:
            s.get(SEARCH, params={"fromMenu": "true", "toggleLanguage": "en"}, timeout=30).raise_for_status()
            first = s.get(SEARCH, params={"fromMenu": "true", "toggleLanguage": "en", "isSecondPartOfPage": "1",
                                          "isInitialNetworkCheck": "1"}, timeout=30)  # without it: "Lost Connection"
            first.raise_for_status()
        except Exception as e:  # noqa: BLE001
            logger.warning("[gcjobs] session/search failed (attempt %d): %s", attempt, str(e)[:120])
            first = None
        if first is not None and "Lost Connection" not in first.text:
            break
        if first is not None:
            logger.warning("[gcjobs] session rejected (Lost Connection page, attempt %d)", attempt)
            first = None
        time.sleep(3)
    if first is None:
        return []
    rows.extend(parse_results(first.text))
    pages = min(total_pages(first.text), max_pages)
    for page in range(2, pages + 1):
        time.sleep(delay)
        try:
            r = s.get(SEARCH, params={"requestedPage": page, "fromPage": 1, "tab": 1, "log": "false",
                                      "isSecondPartOfPage": 1}, timeout=30)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            logger.warning("[gcjobs] page %d failed: %s", page, str(e)[:120])
            continue
        if "Lost Connection" in r.text:
            logger.warning("[gcjobs] session lost at page %d", page)
            break
        rows.extend(parse_results(r.text))

    kept: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        if r["poster"] in seen:
            continue
        seen.add(r["poster"])
        loc, title = r["location"].lower(), r["title"].lower()
        if not any(x in loc for x in locs):
            continue
        if keywords and not title_matches(r["title"], keywords):
            continue
        if any(w in title for w in exclude) or any(o in r["organization"].lower() for o in bad_orgs):
            continue
        # The candidate is not a citizen: PSEA s.39 preference makes core-public-service hires near-impossible.
        if cfg.get("separate_employers_only") and not any(x in r["organization"].lower() for x in non_psea):
            continue
        kept.append(r)

    out: list[RawJob] = []
    for i, r in enumerate(kept):
        url = f"{HOST}/psrs-srfp/applicant/page1800?poster={r['poster']}"
        desc = ""
        if i < max_details:
            time.sleep(delay)
            try:
                d = s.get(HOST + "/psrs-srfp/applicant/page1800", params={"poster": r["poster"]}, timeout=30)
                d.raise_for_status()
                external, desc = parse_detail(d.text)
                if external:
                    url = external
            except Exception as e:  # noqa: BLE001
                logger.warning("[gcjobs] detail %s failed: %s", r["poster"], str(e)[:120])
        org = r["organization"]
        separate = any(x in org.lower() for x in non_psea)
        pref = ("separate employer — no citizen preference" if separate
                else "federal public service — preference to Canadian citizens (PSEA s.39)")
        lang = r["language"] or "language requirement not stated"
        location = r["location"]
        if "various" in location.lower() and "canada" not in location.lower():
            location = f"{location}, Canada"
        header = f"GC Jobs · {lang} · {pref} · closes {r['closing'] or '?'} · {r['salary']}".strip(" ·")
        out.append(RawJob(
            url=canonical_url(url), title=r["title"], company=org.split(" - ")[0].strip(), source=NAME,
            location=location, description=truncate(f"{header}\n\n{desc}") if desc else "",
            snippet=snippet_of(header), salary_currency="CAD" if r["salary"].startswith("$") else None,
            remote=True if re.search(r"telework|remote|virtual", location, re.I) else None,
            extra={"no_fingerprint": True, "poster": r["poster"], "language": lang, "bilingual": "bilingual" in lang.lower(),
                   "psea_preference": not separate, "closing": r["closing"]},
        ))
    logger.info("[gcjobs] %d jobs (%d postings crawled, %d pages)", len(out), len(rows), pages)
    return out

# Shortlist: new sources for Europe-wide remote roles

Research date: 2026-09-28. All probes run from saunalserver (residential IP, Canada) with curl or python. The pipeline repo was not modified.

"Ops-role volume" means titles like operations/revops/bizops/sales ops/project coordinator/ops analyst. It is counted **before** the pipeline's seniority and prefilter cuts, so expect about half of it to survive.

**Residence granularity** means: can the source tell apart "remote, but only if you live in country X" from "remote anywhere, including Canada"? This matters because the candidate lives in Vancouver. Most EU "remote" jobs actually require residence in one EU country. For him that works only if he moves back, and today's scorer treats remote-France/EU as acceptable.

---

## Ranked recommendations

| # | Source | Access | Verified live | Ops volume (remote, EU+CA) | Residence granularity | Effort | Risk | Priority |
|---|---|---|---|---|---|---|---|---|
| 1 | **Workable job search (jobs.workable.com)** | hidden JSON API | ✅ 200 | ~25/day Europe, ~2/day Canada (query "operations") | good (`workplace` + per-country `location`) | S–M | low–med | **HIGH** |
| 2 | **Himalayas: add EU countries** | official API (already integrated) | ✅ 200 | ~1–3/day per country after filters | good (`locationRestrictions` list) | **S (config + 3 params)** | low | **HIGH** |
| 3 | **Remote Rocketship** | Next.js SSR `__NEXT_DATA__` per title×region page | ✅ 200 | ~50/week Europe across 7 title pages | good (`location`, `locationCountries`, seniority flags) | M | med | **HIGH** |
| 4 | **Getro VC boards** (Atomico, Point Nine, HV, Speedinvest, MMC, Earlybird, Daphni, Accel…) | public JSON API | ✅ 200 | ~10–20/week EU-remote ops across 10 boards | good (`work_mode`, `searchable_locations`, `seniority`) | S–M | low | **MED-HIGH** |
| 5 | **Welcome to the Jungle** (ex-Otta) | Algolia search (public front-end key) | ✅ 200 | ~2/day full-remote, ~5/day incl. partial (mostly FR) | medium (remote = fulltime/partial/punctual; office country) | S–M | med | **MED-HIGH** (best French source) |
| 6 | **Working Nomads** | hidden Elasticsearch `_search` | ✅ 200 | ~1–3/day | good (`locations` array: "Europe", "Canada", "Global"…) | S | low–med | MED |
| 7 | **Indeed via jobspy, EU countries, remote-as-location** | jobspy (already integrated) | ✅ | FR ~23/5d, DE ~29/5d, UK ~5/5d per query (noisy) | country-level only | S (config) | same as now | MED |
| 8 | **Consider VC boards** (Balderton, Notion, Alven, Sequoia, First Round) | hidden JSON API, needs session cookie + CSRF | ✅ 200 (after CSRF) | Balderton: 580 remote jobs total | good (`remote`, `locations`, `jobSeniorities`) | M | med | MED |
| 9 | **LastRound dataset re-probe for EU-remote boards** | existing script, new filter | n/a (same boards) | unknown; one-off discovery | via ATS location text | S | low | MED |
| 10 | **Adzuna EU countries** (fr/gb/de/nl/es…) | official API (already integrated) | ✅ 200 | FR 18, DE 38, ES 49, GB 190 per 7d for "operations remote" (low precision) | none (no remote field) | S–M | low | MED-LOW |
| 11 | **4dayweek.io v2 API** | official free API | ✅ 200 | Canada 42 / UK 55 / FR 3 remote per 14d (ops+business+sales+other) | good (per-location `work_arrangement`) | S | low | LOW-MED |
| 12 | **APEC.fr** | hidden JSON API | ✅ 200 | 1,295 live offers with telework code 20767 (probably "total"), all functions | France-only | M | **high (DataDome)** | LOW-MED |
| 13 | **Arbeitnow** | official free API | ✅ 200 | <1/day relevant | weak (`remote` bool, free-text location) | S | low | LOW |
| 14 | **Remote First Jobs** (ex-JobsCollider) | official free API | ✅ 200 | ~1/day EU/CA ops | weak (≤3 countries, often empty) | S | low | LOW |
| 15 | **Wellfound** | Next.js SSR apolloState | ✅ 200 (today) | ~1–2/day, US-heavy | good (`acceptedRemoteLocationNames`) | M | **high** | LOW |

---

## 1. Workable global job search: HIGH

- **Endpoint:** `GET https://jobs.workable.com/api/v1/jobs?query=<q>&workplace=remote&location=<Country|Europe>&day_range=7`. Pagination uses `nextPageToken` (pass it back as `pageToken`). About 20 results per page.
- **Auth/cost:** none, free. There is no published quota; stay at 1 request per second or slower.
- **Verified:** HTTP 200.
  - `query=operations&workplace=remote&day_range=7`: **987** results worldwide.
  - `location=Europe`: **175**. `Canada`: 15. `United Kingdom`: 11. `France`: 7. `Spain`: 6. `Portugal`: 4. `Germany`: 2. `Netherlands`/`Ireland`: 0 (the country filter seems to match only the exact posting country).
  - Samples: "Revenue Operations Analyst" (CA), "Revenue Systems Manager (Remote)" (FR), "Sales Support & Account Operations…" (FR), "Consulting Operations Manager" (UK).
- **Fields:** `title, company{title,website}, workplace (remote|hybrid|on_site), location{city,subregion,countryName}, locations[] ('TELECOMMUTE', …), employmentType, created, url, description, requirementsSection`.
- **Why it matters:** it covers **every** company on Workable. Today the pipeline only reads Workable boards it already knows by name. Workable is the dominant ATS for European SMEs (Greece, Cyprus, UK, NL, Portugal).
- **Residence:** `workplace=remote` plus `location.countryName` gives "remote within country X". A remote-anywhere posting shows as `TELECOMMUTE` with a country, so it can't be separated perfectly. The description needs checking.
- **Watch out for:**
  - `sort=date` is ignored, but `day_range` works.
  - Multi-country clones: the same role is posted once per country (e.g. "Hebrew Speaking…" in FR/DE/ES/PT). Dedupe on company+title.
  - Language-support BPO roles ("Native Dutch speaking…") are frequent noise.
- **ToS:** undocumented API behind Workable's public job-seeker site. Low-to-medium risk.
- **Effort:** S–M. A new `sources/workable_search.py`: loop over query terms × location in {Europe, France, Canada, United Kingdom}, with `day_range=3`.

## 2. Himalayas with EU countries: HIGH (cheapest win)

- The existing `sources/himalayas.py` loops over `countries`. Today only `[CA]` is configured.
- **Verified** with `q=operations`. Country codes FR/DE/NL/ES/GB/IE/PT all return HTTP 200, with totalCount 551–1370.
- **Caveat 1:** by default a country filter **also returns worldwide jobs**. The top results were identical across countries (for example "Trading Operations associate" for all 7). Add `exclude_worldwide=true` to the country passes and keep one `worldwide=true` pass.
- **Caveat 2:** the default sort is relevance. `sort=recent` returns newest first (verified).
- **Other parameters:** `seniority=Entry-level,Mid-level` and `employment_type=Full Time` also work server-side. `country=FR&exclude_worldwide=true&sort=recent` plus those two filters returned **36** matches (newest 09-21).
- **Residence:** `locationRestrictions` is an explicit country list. `['France']` means remote from France only, and a 200-country EMEA list means EMEA-wide. This is the best granularity of any source.
- **Effort:** S. Config change plus passing `sort`, `exclude_worldwide`, `seniority` and `employment_type` through `_query_defs`. Keep the plain `python-requests` UA: browser UAs get a 403.

## 3. Remote Rocketship: HIGH

- **Access:** SEO pages `https://www.remoterocketship.com/country/europe/jobs/<title-slug>` embed `__NEXT_DATA__` with `pageProps.initialJobOpenings` (the 20 newest), `initialTotalJobCount` and `initialWeeklyNewCount`.
  - `?page=2` is **ignored** (it always serves page 1). That's fine for a daily poll, because each title gets fewer than 20 new jobs per week.
- **Verified** (HTTP 200). Europe counts, total open / new this week:

  | Title slug | Total | New this week |
  |---|---|---|
  | operations-specialist | 114 | 11 |
  | operations-coordinator | 52 | 15 |
  | project-coordinator | 129 | 11 |
  | revenue-operations | 52 | 6 |
  | operations-analyst | 27 | 6 |
  | business-operations | 35 | 2 |
  | sales-operations | 23 | 2 |

  That is **~53 new per week** in Europe for these 7 slugs.
  - The `country/france/...` and `country/canada/...` pages lose the title filter (they return generic listings), so use `europe` plus title slugs. A `worldwide` variant exists but held only 3 jobs.
- **Fields:** `roleTitle, company, location, locationCountries, locationType (remote), employmentType, isEntryLevel/isJunior/isMidLevel/isSenior/isLead, url` (the **direct ATS URL**: greenhouse, personio, workday, workable, bamboohr, pinpoint…), `salaryRange, requiredLanguages, created_at, ghostScore`.
  - Also has FR/DE translations of summaries.
- **Residence:** `location` is usually a single country ("Bulgaria", "United Kingdom"), meaning remote within that country. Multi-country arrays appear when the role allows several.
- **Bonus:** the direct ATS URLs can be harvested to discover new Personio/Greenhouse/Workable EU boards for the ATS source.
- **ToS:** the site sells a premium tier, and scraping the SSR JSON is against the spirit of the site. Medium risk. Keep it to 7–10 requests per day.
- **Effort:** M (HTML fetch + JSON parse + slug list).

## 4. Getro-powered VC portfolio boards: MED-HIGH

- **API:** `POST https://api.getro.com/api/v2/collections/<id>/search/jobs`.
  - Body: `{"hitsPerPage":20,"page":N,"filters":{"work_mode":["remote"]},"query":"operations"}`.
  - The `Accept: application/json` header is required; without it you get **406**.
  - `hitsPerPage` is capped at 20.
- **Collection IDs found** (from each board's `__NEXT_DATA__.props.pageProps.network.id`), with remote+"operations" totals:

  | Board | ID | Remote+"operations" | New in 7d |
  |---|---|---|---|
  | Atomico (careers.atomico.com) | 36986 | 147 | 4 |
  | Point Nine (jobs.pointnine.com) | 1680 | 65 | 10 |
  | HV Capital (jobs.hvcapital.com) | 234 | 38 | |
  | MMC (jobs.mmc.vc) | 2303 | 39 | |
  | Speedinvest (careers.speedinvest.com) | 947 | 34 | |
  | Earlybird (jobs.earlybird.com) | 617 | 5 | |
  | Daphni, FR (talent.daphni.com) | 3359 | 1 | |
  | Accel | 8672 | 1102 | |
  | General Catalyst | 222 | 1051 | |
  | Insight | 246 | 664 | |

  - Accel, General Catalyst and Insight are US-heavy, but they do return EU and Canada rows.
- **Fields:** `title, organization{name,industryTags,headCount}, work_mode (remote|hybrid|on_site), searchable_locations[] (e.g. ["Europe","Remote"], ["British Columbia, Canada"]), seniority (entry_level|associate|mid_senior|senior|director|internship), created_at, url` (original ATS link).
- **Residence:** `searchable_locations` distinguishes "Europe/Remote" from a specific country.
- **Samples:** "Deal Operations Manager - Canada, Europe" (Storyblok), "GTM Strategy & Operations Analyst" (Atomico board), "Payments & Fraud Operations Specialist" (Speedinvest).
- **Dead or not Getro:** no board found for Index, Balderton (Consider), Seedcamp, Partech, Kima, LocalGlobe, Creandum, Northzone or Cherry at the guessed hosts. EQT Ventures' board sits behind Cloudflare Access.
- **Effort:** S–M. One source module plus a list of IDs. **Risk:** low. The API is what the public boards call, with no auth.

## 5. Welcome to the Jungle (and Otta, which merged into it): MED-HIGH for France

- **Access:** Algolia `POST https://CSEKHVMS53-dsn.algolia.net/1/indexes/wttj_jobs_production_fr/query`.
  - Headers: `X-Algolia-Application-Id: CSEKHVMS53`, `X-Algolia-API-Key: 4bd8f6215d0cc52b26430765769e65a0` (WTTJ's own public search-only front-end key, visible in any browser session; not a pipeline secret), plus `Referer`/`Origin: https://www.welcometothejungle.com`.
  - The key no longer appears in the new turbopack HTML, but it still works. It may rotate; if it does, grab it from a browser devtools session.
- **Verified:** HTTP 200. The index holds **89,921** jobs.
  - By country: FR 59,989, US 17,793, GB 5,169, **CA 1,809**, DE 1,044, ES 942.
  - By remote type: fulltime 6,290, partial 13,693, punctual 11,740.
- **Filters that work:** `contract_type:full_time AND experience_level_minimum<=3 AND published_at_timestamp>…` plus `remote:fulltime`, and facets on `offices.country_code`.
  - Last 7 days, with a title-restricted query: **12** full-remote hits and **33** full-or-partial hits across ~13 ops terms. Examples: "Operations Specialist" (Zeffy, FR), "Business Ops / Automation & AI H/F (CDI)", "Sales Operations Specialist" (iBanFirst).
- **Fields:** `name, organization{name,slug,nb_employees}, offices[{city,country_code}], remote, contract_type, experience_level_minimum, salary_*, published_at, slug, language, key_missions, summary`.
  - Job URL: `https://www.welcometothejungle.com/fr/companies/<org.slug>/jobs/<slug>`.
- **Residence:** `remote:fulltime` plus the office country in practice means "full remote from France". There is no explicit "anywhere" flag.
- **Why:** it is the #1 French startup/scale-up board. It is strong on exactly his profile (ops, RevOps, automation, bilingual) and includes CDI (permanent) roles.
- **Risk:** medium. It's an undocumented use of a front-end search key.

## 6. Working Nomads: MED

- **Access:** the public feed `GET https://www.workingnomads.com/api/exposed_jobs/` works (200) but returns only **53** jobs. The better path is the Elasticsearch endpoint the site itself uses:
  - `POST https://www.workingnomads.com/jobsapi/_search`
  - Body example: `{"size":100,"sort":[{"pub_date":"desc"}],"query":{"bool":{"must":[{"multi_match":{"query":"operations coordinator revops","fields":["title"]}}],"filter":[{"range":{"pub_date":{"gte":"now-7d"}}},{"terms":{"locations":["Europe","France","Canada","Anywhere","Worldwide","Global","EMEA"]}}]}}}`
- **Verified:** HTTP 200.
  - 1,592 jobs posted in 7 days. 271 of those are tagged Europe/France/Canada/Global/EMEA. Ops-title jobs among those 271: **11**.
  - Aggregations are blocked (the query errors); plain queries are fine.
- **Fields:** `title, company, category_name, locations[], location_base, experience_level (MID_LEVEL…), position_type (ft), apply_url` (direct ATS), `salary_range, pub_date, expired`.
- **Residence:** the `locations` array is clean and explicit ("USA, Canada", "Europe", "Spain", "EMEA").
- **Risk:** low–medium. An open ES endpoint could be closed at any time. **Effort:** S.

## 7. jobspy / Indeed for EU countries, using "remote" as the location: MED (config only)

- **Verified in this venv** (python-jobspy 1.1.82):
  - `country_indeed='france', location='Télétravail'`: 23 results, all `is_remote=True`.
  - `country_indeed='germany', location='Homeoffice'`: 29, all remote.
  - `country_indeed='uk', location='Remote'`: 5.
  - Indeed normalises these to locations like "Télétravail, FR", "Home Office, DE" and "Remote, GB".
- **Noise:** high for FR. The OR-query returned sales agents and freelancers. Run one query per term; don't OR them.
- **LinkedIn "European Union" / "France" with `is_remote=True`: the remote filter does NOT work.** jobspy sends `f_WT=2`, but the guest endpoint returned 50/50 on-site rows (Frankfurt, Warsaw, Paris offices) plus Jobgether. The `is_remote` column is keyword-guessed. LinkedIn EU is only useful if you accept on-site/hybrid rows and filter afterwards. Not recommended for this goal.
- **Residence:** country-level only.

## 8. Consider-powered VC boards: MED

- **Boards:** Balderton (careers.balderton.com, board id `balderton-capital`), Notion Capital (jobs.notion.vc, `notion-capital`), Alven, FR (jobs.alven.co, `alven`), Sequoia (jobs.sequoiacap.com), First Round (jobs.firstround.com).
- **API:** `POST https://<host>/api-boards/search-jobs`.
  - Body: `{"meta":{"size":50},"board":{"id":"<board>","isParent":true},"query":{"remoteOnly":true},"grouped":false}`.
  - It returns **412 INVALID_CSRF** unless you first GET `/jobs` (which gives the `session` cookie and `csrfToken` embedded in the HTML) and send the token as `x-csrf-token`. With that it returns **200**.
- **Verified:** Balderton `remoteOnly` total = **580**.
  - Fields: `title, companyName, locations[], normalizedLocations, remote, hybrid, jobSeniorities, jobFunctions, minYearsExp, url, timeStamp`.
  - Samples: Revolut "Acquiring Sales Executive" with locations "Germany - Remote / Ireland - Remote / …", and a Primer role (UK/HU/PL/PT/IE/RO).
- **Effort:** M (the CSRF dance). **Risk:** medium.

## 9. LastRound dataset: re-probe for EU-remote: MED (one-off discovery)

- `data/lastround-ats-directory.csv` has 9,935 boards (greenhouse 4,966 / ashby 2,856 / lever 2,113). There is **no country column**. `scripts/expand_ats_boards.py` keeps boards with ≥1 posting matching `CANADA_MARKERS`.
- An EU variant needs a second marker set, e.g. "Remote - Europe", "EMEA", "Remote, France", "Europe (Remote)", "CET", "Remote - UK", and a separate `--min-eu` threshold. The 30-day probe cache means only the parse changes; boards already probed are re-evaluated for free.
- There is no dataset covering Personio/Recruitee/Teamtailor/Join. The practical discovery path for those is to harvest ATS slugs from the direct `url` fields that Remote Rocketship, Getro and Working Nomads return (personio, teamtailor, pinpointhq, bamboohr, recruitee hosts all appeared in samples).

## 10. Adzuna in other EU countries: MED-LOW

- The same key works. `what=operations remote`, `max_days_old=7`, `sort_by=date` returned HTTP 200 everywhere: fr 18, gb 190, de 38, nl 15, es 49. `operations télétravail` (fr) returned 6, all on-site "Chargé d'opération" (construction).
- There is **no remote field**. Adding "remote" to the query matches the body text, so precision is poor. Many hits look like gig/AI-training listings ("Operations Management Expert - Remote", "Sales / Revenue / CS Operations Expert"), which appear in every country.
- **Code change:** `adzuna.py` reads a single `profile.country`, so a `countries:` loop is needed (S–M).
- Worth it only for gb (volume) and fr. Rely on the prefilter.

## 11. 4dayweek.io v2 API: LOW-MED

- **Docs:** https://4dayweek.io/developers. Free, no auth, 60 requests/min per IP.
- **Endpoint:** `GET /api/v2/jobs?work_arrangement=remote&country=<Country>&posted_after=14&category=operations,business,sales,project-management,other&limit=100`.
- **Verified 200:** Canada 42, UK 55, Spain 11, Germany 10, France 3, Netherlands 3.
  - Samples: "Success Operations Analyst I" (CA), "Global Entity Operations Associate" (ES/PT/HR).
  - Fields include `level`, `contract_type` (permanent) and per-location `work_arrangement`.
- **Freshness:** the v1 meta shows an "early_access_cutoff" about 2 days behind. The public API lags by about 48h.
- Small but clean, with good residence data. **Effort:** S.

## 12. APEC.fr: LOW-MED

- **Endpoint:** `POST https://www.apec.fr/cms/webservices/rechercheOffre` (JSON, no auth). **200**. 9,375 "cadre" offers match "chargé des opérations".
- **Filter:** `typesTeletravail:["<code>"]`. Code counts: 20765 = 14,119 (likely partial), 20766 = 1,554 (occasional), **20767 = 1,295 (likely full remote; not confirmed)**, 20949 = 1,510 (none).
- **Downsides:** France-residence roles, heavy engineering/industrial noise, and the site runs **DataDome** (`ddjskey` present). Blocking risk is high if polled often.

## 13–15. Low priority (details)

- **Arbeitnow** (`https://www.arbeitnow.com/api/job-board-api?page=N`). Official, free, no key. **200**.
  - About 326 jobs on page 1, then 100 per page. Page 40 is empty, so there are roughly 3k live jobs.
  - Only about 6% have `remote=true`, and the `?remote=true` parameter is **ignored**.
  - Mostly German/UK on-site roles. Relevant remote ops: under 1/day.
- **Remote First Jobs** (JobsCollider now redirects here). Free API `/api/search-jobs?query=&category=business|project-management&page=0-4`, 100 per page, **24h delay**, 200.
  - Of 1,000 business/PM jobs (5 weeks), 437 were EU/CA/unrestricted and 56 were junior/mid ops. Empty `locations` usually means US.
  - URLs point to their own site, not the ATS. ToS: credit them, don't republish.
- **Wellfound.** `https://wellfound.com/role/r/<role>` and `/role/l/<role>/europe` SSR pages returned 200 today with `apolloState` JobListing objects.
  - Fields: `remote, locationNames, acceptedRemoteLocationNames, yearsExperienceMin, liveStartAt`.
  - Sample page role/r/operations-manager: 39 listings, 8 from the last 7 days.
  - Mostly US; applying requires a Wellfound login. DataDome has blocked it historically, so expect it to break.

---

## Rejected

| Source | Reason (verified 2026-09-28 unless noted) |
|---|---|
| EU Remote Jobs (euremotejobs.com) | `/?feed=job_feed` and WP REST `job-listings` both return **401 "Not available"**. `/feed/` is blog posts only. The HTML list shows about 6 jobs. |
| No Fluff Jobs | `/api/posting` returns 200, but it is a 136 MB dump of 17,947 postings, 16k of them in Poland, IT-centric and mostly B2B-contract. `fullyRemote` is false on every row. Wrong market. |
| JustJoin.it | API v2 returns **503** (blocked/changed). Polish IT market anyway. |
| Landing.jobs | API 200, but `remote=true` gives **9 jobs, all engineering** (Portugal tech). |
| Berlin Startup Jobs RSS | 200, 12 items: German-language roles, internships, on-site Berlin. |
| Pangian | Domain parked: HTML is a JS redirect to `/lander`. |
| remote-europe.com | TLS certificate mismatch (site effectively dead). |
| Europe Remotely (europeremotely.com) | 403 to non-browser clients. |
| startup.jobs | 403 (Cloudflare). |
| remote.co | Connection timeout / HTTP2 reset from this IP. |
| Dynamite Jobs | Captcha page, client-rendered, no data in HTML. |
| remote.io | JS-only shell, no SSR data. |
| Relocate.me | Relocation (on-site abroad) board: the opposite of the remote goal. |
| eu-startups.com/jobs | 403. |
| LinkedIn "European Union" remote via jobspy | `f_WT=2` is ignored by the guest endpoint: 50/50 results on-site, plus Jobgether rows (disqualified). |
| France Travail API | 401 without OAuth. It is free with registration but not verified here; mostly on-site French jobs. Revisit only if APEC/WTTJ are not enough. |
| Remotive / RemoteOK / Jobicy | Already dead in the pipeline. Remotive's API still answers 200, but earlier runs showed 0 useful results. |
| Otta | Merged into Welcome to the Jungle (#5). |
| Teamtailor / Join.com / Personio directories | No public cross-company search (join.com `/api/public/jobs` returns 404). Discover these via ATS-URL harvesting (§9). |

## Implementation order (suggested)

1. Himalayas config: add FR, GB, DE, NL, ES, IE, PT, BE with `exclude_worldwide`, `sort=recent` and the seniority/employment filters. About 30 minutes.
2. Workable search source (new module, about 80 lines, same shape as `adzuna.py`).
3. Getro source (list of collection IDs, `work_mode=remote`, drop `senior/director/internship` server-side via the `seniority` field).
4. Remote Rocketship (7–10 title slugs × `country/europe`), with ATS-URL harvesting feeding `ats_boards`.
5. WTTJ Algolia (France), then Working Nomads ES.
6. jobspy Indeed passes for france/Télétravail, germany/Homeoffice, uk/Remote. Measure the prefilter survival rate for two weeks before keeping them.

Across all of these, dedupe on canonical ATS URL. Getro, Remote Rocketship, Working Nomads and Consider all return the underlying Greenhouse/Lever/Ashby/Personio URL, which will overlap with the existing `ats_companies` source.

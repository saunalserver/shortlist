# Shortlist: France / French-language job sources (research 2026-09-28)

Everything below was probed from saunalserver on 2026-09-28. "Verified" means I hit the
endpoint from this machine and got real job data back. I did not edit anything in the pipeline repo.
The Adzuna and Jooble keys were loaded from `.env` into shell variables and never printed.

## TL;DR ranking

| # | Source | Access | Verified | Remote filter | Matching volume (est.) | Effort | Risk |
|---|---|---|---|---|---|---|---|
| 1 | **Welcome to the Jungle (Algolia index)** | Hidden public Algolia search key | YES, 200, 89,921 jobs in index | YES, `remote:fulltime` facet | ~15 FR CDI "operations"-titled jobs/day; 1,070 FR CDI jobs/day overall | S | Medium: unofficial key, needs a Referer header |
| 2 | **LinkedIn + Indeed France via python-jobspy** (already installed) | Scraper, config-only change | YES (LI 30-50/query, Indeed 32 in 7d for one OR-query) | Unreliable in FR (see notes) | High | S | Same as today's Canada use |
| 3 | **APEC** (cadres) | Hidden JSON `POST /cms/webservices/rechercheOffre` | YES, 200 | YES, `typesTeletravail` (code mapping TBD) | Large but noisy (full-text) | M | Medium-high: DataDome protects the rest of the site |
| 4 | **Adzuna FR** | Official API, same key | YES, 200 | No param; phrase-match "télétravail"/"full remote" | Thin for EN titles (e.g. revenue operations 6/wk, sales operations 33/wk) | S (change `country`) | Low |
| 5 | **France Travail "Offres d'emploi v2"** | Official OAuth2 API | PARTIAL (token + search endpoints are live, 400/401 without creds; needs free signup) | NO remote parameter | Very large, mostly non-tech; filter by `qualification=9` (cadre) | M | Low (official) |

Next tier: Teamtailor RSS and Welcome Kit embed per-company feeds, plus a **France re-probe of the
LastRound ATS directory**, then HelloWork, Jooble-FR, Careerjet, Station F, Jobs That Make Sense.

## Key caveat first: living in Canada vs "full remote" in France

- **No source lets you filter for "open to people living outside France".** WTTJ `remote=fulltime`, APEC
  "télétravail total" and HelloWork `t=Complet` all mean *full remote inside France*. A French CDI
  normally needs French residency, because the contract falls under French law and French social security
  (sécu/URSSAF). An employer can only take on someone living in Canada through an EOR (Employer of Record),
  or with "remote from anywhere / EMEA+Americas" wording.
- The practical approach is to **collect "full remote" jobs from French sources, then let the LLM scorer
  look for residency wording** ("remote from anywhere", "EU/EMEA timezone", "must reside in France",
  "Canada"). Tag everything else as **FR-onsite/hybrid (relocation needed)** so it is kept separate.
- **Bonus:** the WTTJ index also carries **Canadian and US offices** (the "operations" query returned
  390 CA-office jobs). The same code can feed the existing Canada search too.

## Key caveat second: French title traps (these will flood the prefilter)

- **"Chargé(e) d'opération(s)"** in France mostly means a construction / public-works / social-housing
  project manager (maîtrise d'ouvrage, MOEX, réhabilitation). In APEC, Indeed FR and France Travail,
  most results for this title were construction jobs. Exclude titles that contain *bâtiment, travaux,
  réhabilitation, construction, MOEX, immobilier, VRD, infrastructures, logement*.
- **"opérations"** stems to **"opérateur/opératrice"** (factory operator) in Adzuna FR, APEC and Meteojob.
  Search on specific phrases in the title, never on the bare word.
- Useful French title phrases: *chargé(e) des opérations* (with "des"), *analyste opérations*,
  *business operations*, *revenue operations / RevOps*, *sales ops / sales operations*, *growth ops*,
  *ops manager* (check seniority), *chef de projet opérations*, *responsable des opérations* (often senior),
  *automatisation / no-code / low-code*, *customer ops*, *bizops*.

---

## 1. Welcome to the Jungle: public Algolia index (TOP PICK)

- **Access:** `POST https://csekhvms53-dsn.algolia.net/1/indexes/wttj_jobs_production_fr/query`
  - Headers: `X-Algolia-Application-Id: CSEKHVMS53`,
    `X-Algolia-API-Key: 4bd8f6215d0cc52b26430765769e65a0` (the public, search-only key that the website
    itself ships to every visitor), **`Referer: https://www.welcometothejungle.com/`**. Without the Referer
    header the call returns 403.
  - The site is now Next.js and CloudFront returns 403 to fast scrapers of the HTML/JS. The Algolia
    endpoint itself answered without trouble.
- **Verified:** YES, HTTP 200. The index holds 89,921 jobs.
  - Query "operations": 13,800 hits.
  - Filters: `offices.country_code:FR AND contract_type:full_time` plus
    `published_at_timestamp > now-7d` gives 1,187 hits, or **111 when restricted to the title**
    (`restrictSearchableAttributes:["name"]`).
  - Last 24h, all FR full-time jobs: 1,070.
- **Facets and fields per hit:**
  - `remote` ∈ {fulltime, partial, punctual, no, unknown}
  - `contract_type` ∈ {full_time (the CDI equivalent), internship, temporary, apprenticeship, freelance, vie…}
  - `experience_level_minimum` (years: 0, 1, 2, 3, 5…), which works as a junior filter
  - `language` (fr/en)
  - `offices[].country_code/city`
  - `salary_*`
  - `organization.{name,slug}`
  - `summary`, `key_missions`, `profile` (enough text for scoring; no full description)
  - `published_at`
  - `slug`, from which the URL is built: `https://www.welcometothejungle.com/fr/companies/{organization.slug}/jobs/{slug}`
- **Remote:** yes. For example, `remote:fulltime AND (offices.country_code:FR OR offices.country_code:CA)`
  over 7 days: operations 24, growth 30, automation 11, business operations 10.
  - Sample hits: "Revenue Strategy & Operations Manager @360Learning (fulltime remote)",
    "Business Ops / Automation & AI H/F (CDI)", "AI Automation Builder (Tech Ops) F/H",
    "Consultant RevOps / Sales Ops".
- **Filter syntax quirk:** filtering by organization works (`organization.slug:payfit`), but restricting
  the search to `organization.name` is refused.
- **Coverage:** WTTJ + Welcome Kit is *the* French startup/scale-up board. Most Next40/120-type companies
  post here: spendesk, payfit, swile, alma, exotec, manomano all have jobs in the index. Some, such as
  qonto, pennylane and alan, were not found under their plain slug; those use Lever/Ashby (see §6).
- **Volume:** ~5-20 relevant FR CDI jobs/day after title filtering; ~1-4/day full-remote.
- **Effort:** S. Build it like the Himalayas source: one POST per query, `hitsPerPage` up to 1000,
  numericFilters on timestamp.
- **Risk:** medium. The key is unofficial but is the one the public site uses; it may rotate (it has been
  the same for years). Fallback: re-read it from the site bundle. Using it is a grey area under the ToS,
  so keep the request rate low (a few queries per run).
- **Priority:** 1.

## 2. LinkedIn + Indeed France via python-jobspy (already in the pipeline)

- **Access:** the existing `autojob/sources/boards.py`. Add a pass with `location="France"` and
  `country_indeed="france"` (LinkedIn also accepts `"European Union"` or `"Paris, Île-de-France"`).
- **Verified:** YES.
  - LinkedIn `location="France"` "operations analyst", 72h: 30 results.
  - LinkedIn "operations" France with `is_remote=True`: 50 results.
  - LinkedIn "revenue operations" in "European Union", remote, 7d: 50 (Mirakl RevOps Analyst Paris,
    GitGuardian Sales Ops Analyst…).
  - Indeed FR, 7d, OR-query ("chargé d'opérations" OR "operations analyst" OR "revenue operations"): 32 results.
- **Remote filter:** **unreliable in France.** `is_remote=True` on LinkedIn France still returned many
  on-site city jobs (e.g. "Responsable d'exploitation, Mondial Relay"). Indeed FR `is_remote` returned
  mostly `is_remote=False`. Treat remote as an LLM/text judgement.
- **jobspy gotchas:**
  - On Indeed, `hours_old` cannot be combined with `job_type`/`is_remote`. With `job_type="fulltime"`
    plus `hours_old`, one query returned only 2 results.
  - Glassdoor FR and Google Jobs via jobspy are **dead** (Glassdoor 400 "location not parsed",
    Google returns 0 results).
- **Volume:** high (tens per query per day); precision is medium.
- **Effort:** S (config only, plus adding "France" to the location logic in the prefilter).
- **Risk:** same as the current Canada scraping (LinkedIn rate limits).
- **Priority:** 2.

## 3. APEC: hidden JSON search (cadre jobs, good fit for a Master's profile)

- **Access:** `POST https://www.apec.fr/cms/webservices/rechercheOffre` with a JSON body, no auth:
  ```json
  {"motsCles":"business operations","typesContrat":["101888"],
   "typesTeletravail":["<code>"],
   "sorts":[{"type":"DATE","direction":"DESCENDING"}],
   "pagination":{"range":100,"startIndex":0},"activeFiltre":true}
  ```
  `101888` = CDI.
- **Verified:** YES, 200.
  - Fields: `numeroOffre`, `intitule`, `nomCommercial`, `lieuTexte`, `salaireTexte`, `texteOffre`
    (~300-character excerpt), `datePublication`, `typeContrat`, `idNomTeletravail`.
  - Totals: "business operations" 732 CDI, "revenue operations" 23, "sales ops" 13, "analyste opérations" 123.
    All of the top 100 by date were from the last 7 days.
  - The response also returns facets (`offreFilters`: experience, company type, location…).
- **Remote:** YES, `typesTeletravail` works. Codes seen: 20765 (2,155), 20766 (1,484), 20949 (1,354),
  20767 (165, the rarest).
  - **The code→label mapping is not confirmed.** 20767 is plausibly "télétravail total", but its sample
    jobs (maintenance technicians) make that doubtful.
  - Confirm the mapping once in a browser: tick "Télétravail total" on apec.fr and read the XHR body.
- **Detail page:** `https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{numeroOffre}`.
  The JSON detail endpoint and the HTML pages are behind **DataDome** (403 from curl); the search
  endpoint was not blocked.
- **Noise:** keyword search is full-text and loose ("operations manager" returns maintenance
  technicians), so title filtering on our side is mandatory.
- **Effort:** M.
- **Risk:** medium-high. The API is undocumented, DataDome is present, and APEC could lock it down.
  Keep volume low (≤ 10 requests/run).
- **Priority:** 3.

## 4. Adzuna France (zero-cost reuse of the existing key)

- **Access:** `GET https://api.adzuna.com/v1/api/jobs/fr/search/{page}`. Same app_id/app_key as Canada.
  The existing `adzuna.py` already builds its URL from `profile.country`. It would need a per-pass country
  setting and `salary_currency="EUR"`.
- **Verified:** YES, 200. 7-day title-only counts:

  | Title query | All contracts | With `permanent=1` |
  |---|---|---|
  | revenue operations | 6 | 0 |
  | business operations | 4 | — |
  | sales operations | 33 | — |
  | operations analyst | 12 | — |
  | ops | 47 | — |
  | chargé opérations | 141 | 28 |

  Many ads carry no contract tag, so `permanent=1` drops them. Do not use `permanent=1`; filter "CDI"
  from the text instead. Note `contract_type=permanent` is **not** a valid parameter (it returns 400).
- **Remote:** no parameter. `what_phrase=full remote` + `what_or=operations ops` returned 34 jobs in 7d,
  including "Revenue Strategy & Operations Manager", "Tech & Automation Ops".
- **Gotcha:** "opérations"/"operations" stems to "opérateur" (9,567 hits, mostly factory work).
  Use phrases only.
- **Effort:** S.
- **Risk:** low (official API, and it shares the existing quota).
- **Priority:** 4. Cheap to add, low yield.

## 5. France Travail "API Offres d'emploi v2" (official)

- **Access:** register (free) at francetravail.io, create an application, subscribe to "API Offres d'emploi".
  - OAuth2 client_credentials against
    `https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire`,
    with scopes `api_offresdemploiv2 o2dsoffre`.
  - Search endpoint: `GET https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search`.
- **Verified:** partially. The token endpoint is live (400 with fake creds) and the search endpoint is live
  (401 without a token). Not tested with real credentials.
  - The public site `candidat.francetravail.fr/offres/recherche?motsCles=…&typeContrat=CDI` returned 200
    with 1,129 CDI hits for "chargé opérations". That page is an HTML fallback, 20 results per page.
- **Quota:** "10 appels / seconde" (data.gouv listing). An older wrapper says 3/s.
  - Max 150 results per call via `range=0-149`; start index capped around 1000-3000.
- **Parameters:** `motsCles` (comma-separated, ≤7), `typeContrat=CDI`, `publieeDepuis` ∈ {1,3,7,14,31},
  `qualification=9` (cadre), `experience` (1 = <1 yr, 2 = 1-3 yrs), `codeROME`, `departement`/`region`,
  `tempsPlein`, `origineOffre` (1 = FT, 2 = partner sites), `sort=1` (by date).
- **Remote:** **no telework search parameter** in the documented list. You would have to grep the
  description for "télétravail"/"100% télétravail".
- **Fit:** huge volume but skewed towards non-cadre and public/SME jobs. It also includes partner-board
  offers. Always use `qualification=9`, and ideally ROME codes, e.g. M1402 (organisation/management
  consulting), M1403 (études/prospectives), M1703 (product/marketing management), N1301/N1302 (supply chain).
- **Effort:** M (OAuth token caching + range paging).
- **Risk:** low. Official and ToS-clean.
- **Priority:** 5. Official and stable, but low precision for startup ops roles.

---

## 6. Company boards (French scale-ups): extend the existing ATS source

Probe results for ~40 well-known French scale-ups:

| ATS | Companies verified |
|---|---|
| **Greenhouse** | mirakl, doctolib, dataiku, ivalua |
| **Lever** | qonto (38 jobs), contentsquare (31), blablacar (14), swile (31), agicap (33), aircall (77), malt (32), pigment (137) |
| **Ashby** | alan (117), qonto (38), doctolib (151), backmarket (34), ledger (7), pennylane (153), sorare (4), swan (7) |
| **Teamtailor** | payfit (12 items), yousign (14), ornikar (17), sunday (52), deezer, hivebrite, swile |
| Not found on any of these | vestiaire-collective, shift-technology, sezane, getaround, lydia, libeo, luko, spliiit (likely WTTJ/Welcome Kit or in-house) |

Recommendations:

- **The biggest win is a France re-probe of `data/lastround-ats-directory.csv`** (9,936 boards). Today
  `ats_boards` keeps only boards with Canada jobs (823 rows). Run the same probe counting
  France/Paris/EU-remote jobs to discover French/EU boards.
  - `ats_companies.location_ok()` also needs a France/EU branch, because it currently drops anything not
    Canada/remote.
- **New: Teamtailor.** `https://{slug}.teamtailor.com/jobs.rss` is public and needs no key. **Verified.**
  - Each item carries the full HTML description, `pubDate`, `link`, **`remoteStatus`**
    (none/hybrid/fully), `tt:locations` (city/country) and `tt:department`.
  - Teamtailor is very common among French/Nordic companies. Effort S. Low risk.
- **New: Welcome Kit (WTTJ's ATS) per-company embed.** **Verified**, 200 JSON with full descriptions:
  `GET https://www.welcomekit.co/api/v1/embed?organization_reference={ref}`
  - Mostly redundant with the WTTJ Algolia index. Useful only for companies that use Welcome Kit
    without a public WTTJ page.
- **Taleez / Flatchr / DigitalRecruiters / Jobaffinity / Talentsoft (Cegid):** only per-company career
  sites; no cross-company public JSON was found.
  - Taleez's API needs each company's own token.
  - DigitalRecruiters exports are token URLs.
  - Not verified; low priority, and many of their customers are SMEs or large corporates rather than startups.

## 7. Other sources checked (lower priority)

| Source | Access | Verified | Remote filter | Notes | Priority |
|---|---|---|---|---|---|
| **HelloWork** | HTML scrape `hellowork.com/fr-fr/emploi/recherche.html?k=…&c=CDI&t=Complet&d=w` | YES, 200, 30 offers/page, job ids `/fr-fr/emplois/{id}.html` | YES: `t=Complet` (full), `Partiel`, `Occasionnel`, `Pas_teletravail` | CDI + full remote, last week: "revenue operations" 5, "business operations" 5. **robots.txt disallows `/fr-fr/emploi/recherche.html`**; Turbo-rendered HTML. | M-low (useful for full-remote FR, but ToS/robots risk) |
| **Jooble FR** | Existing key, `jooble.org/api/{key}` with `location:"France"` | YES, 200 | No (keyword "télétravail") | Thin and stale: "business operations" 39 total, 5 in the last 7d. `fr.jooble.org/api` returns **403 Cloudflare** from the server. A separate FR key (fr.jooble.org/api/about) might give the full FR index; not verified. | Low |
| **Careerjet FR** | Legacy public API `public.api.careerjet.net/search?locale_code=fr_FR&…&affid=…` | YES, 200 once a **Referer header** is sent (48,821 hits for "operations", 99/page) | No (`contracttype=p` = permanent) | Noisy aggregator (retail/logistics). Free affiliate ID recommended. The new v4 API needs a key. | Low |
| **Meteojob** | Undocumented JSON `meteojob.com/api/joboffers/search?what=…` | YES, 200 (139 for "revenue operations") | Field `labels.telework` exists, but ~95% UNDEFINED; filter param not found | Much of it is re-syndicated Jooble (redirect URLs). | Low |
| **Station F / HAL job board** | Welcome Kit Algolia index `wk_cms_jobs_production_careers` (same app id; a 148-char secured key must be read from the hidden `#algolia_api_key` input on jobs.stationf.co/search) | YES, 67 hits for "operations"; `remote` facet has 7 fulltime | YES | Tiny volume; overlaps with WTTJ. | Low |
| **Jobs That Make Sense** (impact/ESS) | HTML scrape (Nuxt SSR), `jobs.makesense.org/fr/s/jobs/all?remote=full` | YES, 200, 20 jobs/page (the query-string search param was not found; one URL gave 500) | YES: `remote=full` | Ops roles in impact organisations; low volume for this profile. | Low |
| **Free-Work** | JSON API `free-work.com/api/job_postings?contracts=permanent&searchKeywords=…` | YES, 200 (59 permanent "operations") | `remoteMode` field (none/partial/full) | IT-centric (IT ops, SOC); poor fit. | Low / skip |
| **Talent.com FR** | HTML | 200 only, not parsed | ? | Aggregator; duplicates others. | Skip |

## 8. Rejected

| Source | Reason |
|---|---|
| Cadremploi | 403 from DataDome bot protection on search. Would need a headless browser. |
| Choose Your Boss | 403 bot protection; IT-developer focused. |
| JobTeaser | 403 plus student/school login required. |
| Glassdoor FR (jobspy) | HTTP 400 "location not parsed". |
| Google Jobs (jobspy `google`) | Returned 0 results. |
| Indeed FR RSS (`fr.indeed.com/rss`) | 404, discontinued. |
| Jobijoba API | 403 "Missing token"; partner-only. |
| Malt | Freelance only. |
| Free-Work freelance side | Freelance (only the CDI subset is usable, see above). |
| WTTJ REST (`api.welcometothejungle.com/api/v1/organizations/{slug}/jobs`) | 404, retired. Use Algolia or the Welcome Kit embed instead. |

## Implementation notes for whoever builds it

1. Add a **"FR pass"** concept: a country/currency per pass (Adzuna, jobspy, Jooble). Tag every job
   `market=FR` and `remote_class ∈ {fr_fullremote, fr_hybrid_onsite}` so the dashboard can separate
   "relocate" from "remote".
2. The prefilter needs FR location markers (France, Paris, Lyon, Île-de-France, "télétravail",
   "full remote", "100% remote") and FR title handling (H/F, F/H, (CDI) suffixes). Also add the
   construction exclusion list above.
3. Seniority words in FR: *Senior, Lead, Head of, Directeur/Directrice, Responsable (often mid-senior),
   Manager (often ok in startups), Confirmé(e) (mid), Junior/Débutant (keep)*. Use WTTJ
   `experience_level_minimum ≤ 3` as a structured filter.
4. The Serper replacement question is unchanged: Google Jobs via jobspy is dead from this box.

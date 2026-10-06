You read one job posting and record FACTS about it for a specific candidate (profile
below). You do NOT pick a score — the score is computed from your answers by code, so
accuracy matters more than generosity. When unsure, choose the more conservative value.

Output ONLY a JSON object matching the schema at the bottom. No markdown, no commentary.

═══════════════════════════════════════════════════════════════════════
1. ROLE FAMILY — what the person does all day (NOT what the title says)
═══════════════════════════════════════════════════════════════════════
Read the duties. A title with "Operations" or "Coordinator" can hide a retail floor,
a call centre or a construction site. Pick exactly one:

Target families (the candidate's work):
  operations              — ops specialist/analyst/coordinator/associate/generalist in a
                            company's business operations: processes, tooling, reporting,
                            cross-team coordination, vendor/partner ops
  bizops_strategy         — business operations, strategy & operations, chief of staff,
                            founder's office, operations strategy
  revops_salesops_gtm     — revenue/sales/marketing/partner/GTM operations: CRM hygiene,
                            pipeline reporting, attribution, lead routing, comp/territory ops
  growth_ops              — growth operations, lifecycle/CRM ops, experiment ops, funnel
                            analytics (running the machine, not creating content)
  implementation_onboarding — implementation/onboarding specialist, solutions consultant,
                            customer onboarding, technical account management (non-quota)
  business_systems_analysis — business analyst, business systems analyst, process
                            improvement, data/reporting operations, BI for an ops team
  automation_ai_ops       — building no-code/low-code/AI workflows and internal tools for
                            the business (Make, n8n, Zapier, Apps Script, LLM agents) —
                            this family applies even when the title says "engineer", as
                            long as the job is not writing production software
  project_program_coord   — project/program coordinator or junior PM in a business or
                            tech setting (NOT construction, engineering or facilities)
  product_ops             — product operations (tooling, feedback loops, launch process)

Adjacent families (sometimes a fit):
  customer_success        — CSM, account management without sales quota, customer ops
  supply_chain_procurement — supply chain / procurement / logistics ANALYST or coordinator
                            at a desk (not warehouse or driving)
  data_analytics          — data/reporting analyst not attached to an ops team
  finance_ops             — finance operations, billing ops, FP&A support, AR/AP systems
  customer_support_ops    — support operations, CX coordinator (not front-line queue work)
  marketing_execution     — marketing coordinator/specialist, performance marketer,
                            content/social, events

Off-target families:
  sales_quota             — AE, SDR/BDR, account executive, business development, any
                            role measured on closing deals or booking meetings
  software_engineering    — writing production code, DevOps, SRE, QA engineering
  data_science_ml         — data science, ML engineering, research
  hr_recruiting           — HR, people ops, talent acquisition, payroll
  retail_hospitality      — store/restaurant/hotel/branch staff or managers
  admin_clerical          — receptionist, office/admin assistant, data entry, clerk,
                            scheduling, front desk, medical office
  call_center             — contact centre, inbound/outbound phone queue, collections
  trades_field_physical   — construction, facilities, warehouse, driving, fleet depot,
                            manufacturing, lab, field service
  healthcare_clinical     — clinical care, rehab, nursing, pharmacy
  legal_compliance        — legal, compliance, AML/KYC review, audit, risk
  finance_accounting      — accountant, bookkeeper, financial analyst needing CPA/CFA,
                            investment/banking roles
  education_other         — teaching, research, creative, anything else

═══════════════════════════════════════════════════════════════════════
2. DUTIES MATCH (0–3) — how squarely the day-to-day is the candidate's work
═══════════════════════════════════════════════════════════════════════
  3 = most duties are things he has done: running/automating an ops process, building
      dashboards and reporting (SQL, Sheets, BigQuery), owning a tool stack, coordinating
      across teams, attribution/funnel analytics, onboarding/partner ops
  2 = clearly overlapping, with some new domain to learn
  1 = a little overlap; the core of the job is something else
  0 = unrelated to his experience
Be strict: "uses Excel" or "detail-oriented" is not overlap. A 3 should be rare.

═══════════════════════════════════════════════════════════════════════
3. OTHER FACTS
═══════════════════════════════════════════════════════════════════════
seniority: entry | junior | mid | senior | lead | manager | executive — from the title
  AND the requirements ("Senior", "Sr", "Lead", "Principal", "Staff", "Head of",
  "Director", "VP", "Chief" titles → senior/lead/executive).
people_manager: true only if the role manages direct reports.
years_required: minimum years of experience stated as REQUIRED (integer), else null.
  "3–5 years" → 3. "Preferred/an asset" years do not count → null.
missing_must_haves: hard requirements (must have / required / minimum) the candidate
  clearly lacks per his profile — degrees, certifications (CPA, PMP), specific platforms
  as core admin work (Salesforce admin, NetSuite), licences, security clearance,
  languages other than EN/FR, N years in a specific domain. Max 3. Nice-to-haves never.
employment_type: permanent | contract | temporary | part_time | internship | unknown.
  Fixed-term, maternity/parental cover, contract-to-hire, CDD, freelance → contract.
  Silent posting → unknown (treated as permanent).
work_mode: onsite | hybrid | remote | unknown.
location_ok: false if ANY applies —
  • on-site or hybrid outside Metro Vancouver (Vancouver, Burnaby, Richmond BC, Surrey,
    Coquitlam, New Westminster, North/West Vancouver, Delta, Langley…);
  • remote but EXPLICITLY restricted to US residents ("US only", named US states, "must
    reside in the US"). A US-based employer or USD salary alone is NOT a disqualifier
    unless Canada-based candidates are excluded — do not infer;
  • remote but EXPLICITLY requires living in a country other than Canada ("must be based
    in France", "UK residents only", "remote within Germany", "EU residents");
  • requires working full European/Asian business hours from Vancouver;
  • employer/payroll based in Africa, Asia, the Middle East, Latin America or Oceania.
  A remote posting that is silent on where you must live is location_ok=true (European
  employers welcome). EU work authorization alone is not a residency rule.
citizenship_required: true if Canadian citizenship/PR or a security clearance requiring
  citizenship is required.
employer_type: startup (<200, venture-backed/young) | smb (<1000) | enterprise (1000+,
  banks, telecoms, big retail) | public_sector (government, crown corp, health authority,
  university) | agency_or_hidden (staffing agency, recruiter, hidden client, "Job
  Application for X at Y" funnels, co-founder/equity-only asks) | unknown
careers_index: true if the page lists many jobs instead of describing one.
signals — include ONLY those clearly present in the posting:
  "automation_ai"     the role involves building automations or AI workflows
  "bilingual_french"  French is required or explicitly valued
  "early_career"      explicitly junior / entry-level / new grad / 0–2 years
  "tool_overlap"      requires or uses ≥2 of: SQL, BigQuery, Google Sheets/Apps Script,
                      Make, n8n, Zapier, Python, PostHog, Customer.io, Everflow, HubSpot
  "candidate_domain"  a domain he has worked in: last-mile/delivery, affiliate/growth
                      marketing, DTC health/telehealth, B2B SaaS ops
  "ownership"         first ops hire / build from scratch / small team with broad scope

═══════════════════════════════════════════════════════════════════════
EXAMPLES (facts, abbreviated)
═══════════════════════════════════════════════════════════════════════
"(CAN) Consumables Department Manager", Walmart, Langley BC
→ role_family retail_hospitality, duties_match 0, seniority manager, people_manager true,
  employer_type enterprise.
"Operations Coordinator", logistics SaaS startup, Vancouver, 1–2 yrs, Sheets + SQL
→ operations, duties_match 3, junior, signals [early_career, tool_overlap,
  candidate_domain], employer_type startup.
"Client Care Coordinator", physio clinic, Surrey — booking patients, front desk
→ admin_clerical, duties_match 0.
"AI Automation Engineer", 7shifts, remote Canada — builds n8n/LLM workflows for GTM teams
→ automation_ai_ops, duties_match 3, signals [automation_ai, tool_overlap].
"Technical Customer Success Manager", SaaS, quota-free, 3+ yrs CSM required
→ customer_success, duties_match 1, mid, years_required 3,
  missing_must_haves ["3+ years as a CSM"].
"Co-Founder Wanted — Sales & Client Acquisition Partner", equity only
→ sales_quota, employer_type agency_or_hidden, employment_type unknown.
"Revenue Operations Analyst", Paris SaaS, full remote, "vous résidez en France"
→ revops_salesops_gtm, location_ok false (explicit French residency).
"Rating Operations Associate – English & French", Canadian edtech, remote Canada
→ operations, duties_match 2, entry, signals [bilingual_french, early_career].

═══════════════════════════════════════════════════════════════════════

{candidate_profile}

═══════════════════════════════════════════════════════════════════════
OUTPUT JSON SCHEMA
═══════════════════════════════════════════════════════════════════════
{
  "company": "<actual employer name>",
  "role_summary": "<one sentence: what this person actually does all day>",
  "role_family": "<one family id from section 1>",
  "duties_match": <0-3>,
  "seniority": "<entry|junior|mid|senior|lead|manager|executive>",
  "people_manager": <bool>,
  "years_required": <int or null>,
  "missing_must_haves": ["<string>"],
  "employment_type": "<permanent|contract|temporary|part_time|internship|unknown>",
  "work_mode": "<onsite|hybrid|remote|unknown>",
  "location_ok": <bool>,
  "location_note": "<short: where / residency rule / why not ok>",
  "citizenship_required": <bool>,
  "employer_type": "<startup|smb|enterprise|public_sector|agency_or_hidden|unknown>",
  "careers_index": <bool>,
  "signals": ["<signal id>"],
  "strengths": ["<max 3, concrete, for this candidate>"],
  "gaps": ["<max 3, concrete>"],
  "one_liner": "<one sentence, all of: the role family in plain words + the industry/product,
                 the years band and salary band IF STATED, the single biggest pro and the single
                 biggest con. Name facts, never verdict filler — 'Strong fit, recommend' / 'Good
                 fit' / 'no hard disqualifiers' are banned (they describe 100% of applies AND
                 85% of dismissals, so they distinguish nothing)>"
}

#!/usr/bin/env python3
"""Seed demo DBs with fully generic fake data (fake companies, fake roles).
Creates: demo/autojob-source/data/autojob.db + demo/dashboard-data/jobsearch.db"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
AUTOJOB_REAL = os.path.join(ROOT, "..", "pipeline", "data", "autojob.db")
DASH_REAL = os.path.join(ROOT, "..", "dashboard", "data", "jobsearch.db")

TODAY = "2026-09-03"
NOW = f"{TODAY} 07:04:11"


def clone_schema(real_path, demo_path):
    os.makedirs(os.path.dirname(demo_path), exist_ok=True)
    if os.path.exists(demo_path):
        os.remove(demo_path)
    src = sqlite3.connect(real_path)
    dst = sqlite3.connect(demo_path)
    for (sql,) in src.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"):
        dst.execute(sql)
    src.close()
    return dst


def J(lst):
    return json.dumps(lst)


# ---------------------------------------------------------------- pipeline db
db = clone_schema(AUTOJOB_REAL, os.path.join(ROOT, "autojob-source", "data", "autojob.db"))

db.execute(
    "INSERT INTO runs (id, started_at, finished_at, status, fetched, new_jobs, prefiltered, scored,"
    " queued, skipped, docs, errors, llm_calls, expired) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    (48, f"{TODAY} 07:00:02", f"{TODAY} 07:11:48", "done", 612, 89, 61, 28, 8, 18, 2, 0, 31, 3),
)
for i, r in enumerate(
    [
        ("2026-09-02 07:00:01", "done", 587, 74, 55, 25, 6, 1, 0, 28, 2),
        ("2026-09-01 07:00:03", "done", 641, 102, 68, 31, 9, 3, 0, 34, 5),
        ("2026-08-31 07:00:01", "done", 529, 61, 49, 22, 5, 0, 1, 26, 1),
        ("2026-08-30 07:00:02", "done", 604, 88, 59, 27, 7, 1, 0, 29, 2),
        ("2026-08-29 07:00:01", "done", 571, 79, 52, 24, 6, 2, 0, 27, 0),
        ("2026-08-28 07:00:02", "done", 598, 91, 57, 26, 7, 0, 0, 30, 3),
        ("2026-08-27 07:00:01", "done", 553, 70, 51, 23, 5, 1, 0, 25, 2),
    ],
    start=41,
):
    db.execute(
        "INSERT INTO runs (id, started_at, finished_at, status, fetched, new_jobs, prefiltered, scored,"
        " queued, skipped, docs, errors, llm_calls, expired) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (i, r[0], r[0].replace("07:00", "07:12"), r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], 2),
    )

for s, dur, got, new in [
    ("greenhouse", 4.2, 118, 21), ("workday", 6.8, 96, 14), ("lever", 3.9, 74, 9),
    ("adzuna", 5.1, 87, 12), ("jooble", 7.4, 112, 15), ("serper", 8.0, 65, 8),
    ("eluta", 4.6, 58, 6), ("jobbank", 3.2, 41, 4),
]:
    db.execute(
        "INSERT INTO source_runs (run_id, source, started_at, duration_s, fetched, new_jobs) VALUES (?,?,?,?,?,?)",
        (42, s, f"{TODAY} 07:00:05", dur, got, new),
    )

db.execute(
    "INSERT INTO pipeline_state (id, status, run_id) VALUES (1, 'idle', 48)"
)

def stamp_n(day_back):
    day = 3 - day_back
    return f"2026-09-{day:02d}" if day >= 1 else f"2026-08-{31+day:02d}"


jobs = [
    # (title, company, score, status, location, source, posted_days_ago, reasoning, strengths, gaps, extra)
    ("Revenue Operations Analyst", "Northwind Traders", 9, "queued", "Vancouver, BC (Hybrid)", "greenhouse", 1,
     "Almost exact overlap with the profile: revenue/reporting automation in Python + SQL, CRM hygiene ownership, weekly exec reporting cadence. Small data team means high ownership from day one.",
     J(["Python + SQL automation in a revenue context", "Owns CRM data hygiene end-to-end", "Recurring exec reporting cadence", "Mid-size company, high ownership"]),
     J(["Salesforce admin cert preferred (HubSpot equivalent held)"]), {}),
    ("Business Systems Analyst", "Contoso", 8, "queued", "Remote (Canada)", "workday", 2,
     "Systems integration + process automation role sits right on the profile's RevOps/BizOps line. Tooling matches (Python, SQL, Workato-class integrations); salary band is at profile target.",
     J(["Integration/tooling stack matches profile", "Fully remote within Canada", "Process documentation valued in JD"]),
     J(["2+ yrs with ERP migrations not evidenced", "Occasional 6am Pacific overlap calls"]), {"salary_min": 95000, "salary_max": 115000, "salary_currency": "CAD"}),
    ("GTM Operations Manager", "Fabrikam", 8, "queued", "Vancouver, BC", "lever", 3,
     "GTM ops role with pipeline analytics and territory design — the analytics half is a direct match. Management scope is a step up but team is three analysts, close to profile appetite.",
     J(["Pipeline analytics core of the role", "Local Vancouver team", "Reporting directly to VP RevOps"]),
     J(["People management not yet held formally"]), {"salary_min": 105000, "salary_max": 125000, "salary_currency": "CAD"}),
    ("Partner Operations Analyst", "Adventure Works", 7, "queued", "Toronto, ON (Remote)", "adzuna", 4,
     "Partner-data operations with heavy Salesforce reporting. Matches the ops-core of the profile; remote-from-BC needs confirming but posting lists Canada-wide remote.",
     J(["Partner data + Salesforce reporting", "Canada-wide remote listed", "Ops-ownership of full lifecycle"]),
     J(["Equity-comp heavy package", "Eastern-time-first meeting culture"]), {}),
    ("Data Operations Specialist", "Fourth Coffee", 7, "queued", "Vancouver, BC", "greenhouse", 2,
     "Supply-chain data ops with pipeline maintenance and vendor-data cleanup — adjacent to profile's data-cleanup strengths, though domain is supply chain rather than revenue.",
     J(["Data pipeline ownership", "Hybrid Vancouver, 2 days on-site", "Clear 90-day success metrics in JD"]),
     J(["Domain shift from revenue to supply chain"]), {}),
    ("CRM & Systems Administrator", "Coho Vineyards", 7, "queued", "Remote (Canada)", "workday", 5,
     "HubSpot administration + lead-routing automation — direct tool match with the profile. Risk: role skews admin (permissions, hygiene) over analysis.",
     J(["Exact HubSpot stack match", "Lead-routing automation projects", "Fully remote"]),
     J(["Light on analysis/reporting scope", "Single-person ops team, limited mentorship"]), {}),
    ("Growth Operations Lead", "A. Datum", 7, "queued", "Vancouver, BC (Hybrid)", "serper", 1,
     "Growth ops in a B2B SaaS: experiment instrumentation, funnel reporting, Martech stack. Matches growth-ops target roles in the profile preferences.",
     J(["Experiment instrumentation + funnel reporting", "Small growth team, broad remit", "Hybrid Vancouver"]),
     J(["Seed-stage — comp may sit below target band"]), {}),
    ("Sales Operations Analyst", "Wingtip Toys", 6, "queued", "Burnaby, BC", "eluta", 6,
     "Classic sales-ops: forecasting hygiene, commission tracking, CRM cleanup. Solid match on skills but scope is narrower than the profile's automation breadth.",
     J(["Forecast + commission ops experience", "Commute-able Burnaby office"]),
     J(["Narrower scope than profile target", "Legacy CRM migration mid-flight"]), {}),
    ("Revenue Systems Analyst", "Proseware", 8, "docs_generated", "Remote (Canada)", "greenhouse", 3,
     "RevOps analyst owning CPQ + billing data flows in B2B SaaS. Direct profile match; docs generated and promoted to tracker.",
     J(["CPQ/billing data flows = profile core", "Remote Canada, async-first", "Ops-owns-its-roadmap culture"]),
     J(["NetSuite exposure shallower than asked"]), {"output_folder": "DEMO_OUT/Proseware__Revenue_Systems_Analyst", "docs_generated_at": f"{TODAY} 06:58:00"}),
    ("RevOps Manager", "Tailspin Games", 8, "docs_generated", "Vancouver, BC (Hybrid)", "lever", 4,
     "First RevOps hire at a gaming studio — build the stack from zero. High autonomy match with the profile's self-directed automation history.",
     J(["Greenfield RevOps build", "Reporting to CFO, high visibility", "Studio's data maturity is low = big wins"]),
     J(["No existing RevOps playbook (build from zero)"]), {"output_folder": "DEMO_OUT/Tailspin_Games__RevOps_Manager", "docs_generated_at": f"{TODAY} 06:57:00"}),
    # unscored new
    ("Marketing Operations Coordinator", "Harborline Logistics", None, "new", "Vancouver, BC", "jooble", 0, None, None, None, {}),
    ("Revenue Analyst", "Quillstack Software", None, "new", "Remote (Canada)", "serper", 0, None, None, None, {}),
    # prefiltered
    ("Senior Civil Engineer", "Adventure Works", None, "prefiltered", "Vancouver, BC", "adzuna", 1, None, None, None, {"prefilter_reason": "title stop-word: civil"}),
    ("Contract Data Entry Clerk", "Contoso", None, "prefiltered", "Calgary, AB", "jooble", 2, None, None, None, {"prefilter_reason": "employment type: contract"}),
    ("Registered Nurse — ICU", "Coho Vineyards", None, "prefiltered", "Saskatoon, SK", "eluta", 1, None, None, None, {"prefilter_reason": "title stop-word: nursing"}),
    # skipped (below the bar)
    ("Insurance Sales Representative", "Fabrikam", 3, "skipped", "Surrey, BC", "adzuna", 5, "Commission-heavy outbound sales; no ops, data or systems component.", None, None, {}),
    ("Junior Office Administrator", "Wingtip Toys", 4, "skipped", "Langley, BC", "jooble", 3, "Entry-level admin with no data or automation scope; well below target seniority.", None, None, {}),
    ("Retail Shift Supervisor", "Fourth Coffee", 3, "skipped", "Vancouver, BC", "eluta", 4, "Retail floor supervision; unrelated to profile targets.", None, None, {}),
    ("Call Centre Team Lead", "Proseware", 4, "skipped", "Abbotsford, BC", "adzuna", 6, "High-volume call centre ops; limited systems/data work.", None, None, {}),
    # expired
    ("BizOps Analyst", "Contoso", 7, "expired", "Vancouver, BC", "workday", 31, "Shortlisted, then retired: posting older than 30 days.", None, None, {"skip_reason": "posting expired (33 days old, link dead)"}),
    ("Revenue Operations Specialist", "Northwind Traders", 7, "expired", "Vancouver, BC", "greenhouse", 29, "Shortlisted earlier; re-posted since as the analyst role above.", None, None, {"skip_reason": "posting expired (30 days old)"}),
    # error (will retry)
    ("Deal Desk Analyst", "A. Datum", None, "error", "Vancouver, BC", "lever", 2, None, None, None, {"skip_reason": "scoring error — provider timeout, will retry next run"}),
]

for i, (title, company, score, status, loc, source, posted_ago, reasoning, strengths, gaps, extra) in enumerate(jobs, start=1):
    row = {
        "url": f"https://jobs.example.com/{company.lower().replace(' ', '-')}/{i}",
        "title": title, "company": company, "fit_score": score, "status": status,
        "fetched_at": f"{TODAY} 07:0{i % 10}:00",
        "location": loc, "source": source,
        "posted_at": stamp_n(posted_ago),
        "remote": 1 if "Remote" in loc else 0,
        "snippet": f"{title} at {company} — {loc}.",
        "fingerprint": f"fp{i:04d}",
        "run_id": 42,
        "scored_at": (f"{TODAY} 07:05:{i:02d}" if score is not None or status == "error" else None),
        "scorer_model": ("gpt-5-mini" if score is not None else None),
        "fit_reasoning": reasoning, "strengths": strengths, "gaps": gaps,
    }
    row.update(extra)
    if status == "prefiltered":
        row["scored_at"] = None
        row["fetched_at"] = f"{TODAY} 07:01:00"
    if status == "expired":
        row["fetched_at"] = f"2026-08-0{i} 07:02:00"
        row["posted_at"] = f"2026-08-0{i}"
    out = row.pop("output_folder", None)
    if out:
        row["output_folder"] = out.replace("DEMO_OUT", f"{ROOT}/autojob-source/output/2026-09-02")
    cols = ",".join(row.keys())
    ph = ",".join("?" * len(row))
    db.execute(f"INSERT INTO jobs ({cols}) VALUES ({ph})", list(row.values()))

db.commit()
db.close()

# -------------------------------------------------------------- dashboard db
db = clone_schema(DASH_REAL, os.path.join(ROOT, "dashboard-data", "jobsearch.db"))

apps = [
    # (company, role, status, applied_days_ago, source, salary, location)
    ("Proseware", "Revenue Systems Analyst", "bookmarked", None, "Pipeline digest", "$105–115k CAD", "Remote (Canada)"),
    ("Coho Vineyards", "CRM & Systems Administrator", "bookmarked", None, "Pipeline digest", "", "Remote (Canada)"),
    ("A. Datum", "Growth Operations Lead", "bookmarked", None, "Pipeline digest", "", "Vancouver, BC"),
    ("Tailspin Games", "RevOps Manager", "applied", 1, "Pipeline digest", "$110k CAD", "Vancouver, BC"),
    ("Contoso", "Business Systems Analyst", "applied", 3, "Pipeline digest", "$95–115k CAD", "Remote (Canada)"),
    ("Adventure Works", "Partner Operations Analyst", "applied", 5, "LinkedIn", "", "Toronto, ON"),
    ("Northwind Traders", "Revenue Operations Analyst", "screening", 2, "Pipeline digest", "$100k CAD", "Vancouver, BC"),
    ("Fabrikam", "GTM Operations Manager", "interview", 8, "Pipeline digest", "$105–125k CAD", "Vancouver, BC"),
    ("Harborline Logistics", "Marketing Operations Specialist", "interview", 12, "Job Bank", "$85k CAD", "Vancouver, BC"),
    ("Fourth Coffee", "Data Operations Specialist", "final_round", 15, "Pipeline digest", "$92k CAD", "Vancouver, BC"),
    ("Quillstack Software", "Revenue Analyst", "offer", 21, "Referral", "$98k CAD", "Remote (Canada)"),
    ("Wingtip Toys", "Sales Operations Analyst", "rejected", 10, "Eluta", "", "Burnaby, BC"),
    ("Proseware", "Deal Desk Analyst", "rejected", 24, "Lever", "", "Vancouver, BC"),
    ("Contoso", "BizOps Analyst", "ghosted", 30, "Pipeline digest", "", "Vancouver, BC"),
]

for i, (co, role, status, ago, src, sal, loc) in enumerate(apps, start=1):
    applied = f"2026-09-{3 - ago:02d}" if ago is not None and ago < 3 else (f"2026-08-{31 - ago + 3:02d}" if ago is not None else None)
    db.execute(
        "INSERT INTO applications (id, company_name, role_title, date_applied, source, status, posting_url,"
        " salary_info, location, notes, tags, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (f"demo-{i:03d}", co, role, applied, src, status, f"https://jobs.example.com/{co.lower().replace(' ', '-')}",
         sal, loc, "", "[]", applied or f"{TODAY}", f"{TODAY} 08:00:00"),
    )
db.commit()
db.close()
print("demo DBs seeded OK")

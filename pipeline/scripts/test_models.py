"""One-shot live test of free-model candidates through the real scorer path (llm.py, json mode).
Run: venv/bin/python scripts/test_models.py"""
import sys, time
sys.path.insert(0, ".")

from autojob.settings import load_settings
from autojob.llm import LLM
from autojob import db

CANDIDATES = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nex-agi/nex-n2.5-pro:free",
    "thinkingmachines/inkling:free",
    "nvidia/nemotron-3.5-lightning:free",
    "cohere/north-mini-code:free",
    "nex-agi/nex-n2.5-mini:free",
    "poolside/laguna-s-2.1:free",
]

settings = load_settings()
system = settings.prompt("scorer").replace("{candidate_profile}", settings.candidate_profile())

job = db.connect().execute(
    "SELECT title, url, company, location, employment_type, source, description "
    "FROM jobs WHERE description IS NOT NULL AND length(description) > 2000 "
    "AND status='queued' ORDER BY fit_score DESC LIMIT 1"
).fetchone()
job = dict(zip(job.keys(), job))
meta = [f"{k}: {job[k]}" for k in ("company", "location", "employment_type", "source") if job.get(k)]
user = f"Title: {job['title']}\nURL: {job['url']}\n" + "\n".join(meta) + \
       f"\n\nFull job description:\n{job['description']}"
print(f"TEST JOB: {job['title']} @ {job['company']}\n")

for name in CANDIDATES:
    llm = LLM(settings.secrets.llm_api_key, settings.secrets.llm_base_url, [{"name": name, "rpm": 20}])
    t0 = time.monotonic()
    try:
        r = llm.chat_json(system, user, temperature=0.2)
        need = {"fit_score", "skip", "one_liner", "strengths", "gaps"}
        missing = need - set(r.keys())
        print(f"OK   {name:45s} {time.monotonic()-t0:5.1f}s  score={r.get('fit_score')} "
              f"skip={r.get('skip')} missing={sorted(missing) or '-'}")
        print(f"     one_liner: {str(r.get('one_liner'))[:140]}")
    except Exception as e:  # noqa: BLE001
        print(f"FAIL {name:45s} {time.monotonic()-t0:5.1f}s  {str(e)[:150]}")

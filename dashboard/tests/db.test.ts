/**
 * Dashboard DB-layer tests (plain asserts, run with tsx — no test framework in this package).
 * Uses throwaway sqlite files in a tmp dir; never touches dashboard/data or the pipeline DB.
 *
 *   cd dashboard && npm test
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import Database from 'better-sqlite3';

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'shortlist-dashboard-test-'));
process.env.AUTOJOB_DB_PATH = path.join(tmp, 'autojob.db');
process.env.DATABASE_PATH = path.join(tmp, 'jobsearch.db');

main().catch(err => { console.error(err); process.exitCode = 1; });

async function main() {

const iso = (daysAgo: number) => new Date(Date.now() - daysAgo * 86400_000).toISOString();

// --- fixture: pipeline jobs table as the current pipeline schema creates it, WITHOUT dismiss_reason
// (so the dashboard's defensive migration is exercised for real)
const fixture = new Database(process.env.AUTOJOB_DB_PATH!);
fixture.exec(`
  CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT, snippet TEXT, description TEXT, company TEXT, location TEXT, source TEXT,
    salary_min REAL, salary_max REAL, salary_currency TEXT, employment_type TEXT, posted_at TEXT,
    remote INTEGER, fingerprint TEXT, fit_score INTEGER, fit_reasoning TEXT, strengths TEXT, gaps TEXT,
    skip_reason TEXT, prefilter_reason TEXT, status TEXT NOT NULL DEFAULT 'new',
    fetched_at TEXT NOT NULL, processed_at TEXT, scored_at TEXT, scorer_model TEXT,
    low_confidence INTEGER DEFAULT 0, description_length INTEGER, output_folder TEXT,
    docs_generated_at TEXT, user_action TEXT, user_action_at TEXT, run_id INTEGER,
    link_checked_at TEXT, score_facts TEXT
  );
`);
const insert = fixture.prepare(`INSERT INTO jobs (url, title, source, status, fetched_at, scored_at,
  fit_score, low_confidence, user_action, posted_at) VALUES (?, ?, 'wttj', ?, ?, ?, ?, ?, ?, ?)`);
let n = 0;
function addJob(o: Partial<Record<'status' | 'scored_at' | 'fit_score' | 'low_confidence' | 'user_action' | 'posted_at', string | number | null>>) {
  const res = insert.run(
    `https://example.com/${++n}`,
    `Job ${n}`,
    o.status ?? 'queued',
    iso(1), // fetched_at
    o.scored_at ?? iso(1),
    o.fit_score ?? 7,
    o.low_confidence ?? 0,
    o.user_action ?? null,
    o.posted_at !== undefined ? o.posted_at : iso(1).slice(0, 10),
  );
  return Number(res.lastInsertRowid);
}

const { getAutojobJobs, getAutojobStats, setUserAction, getExpiringPendingCount } = await import('../lib/autojob-db');


// 1. Defensive dismiss_reason migration (parallel pipeline change; additive, idempotent)
{
  getAutojobJobs(); // first call opens the connection and runs the migration
  const cols = (fixture.pragma('table_info(jobs)') as { name: string }[]).map(c => c.name);
  assert.ok(cols.includes('dismiss_reason'), 'dashboard init must add jobs.dismiss_reason when missing');
  getAutojobJobs(); // idempotent on the next call
}

// 2. Fourteen-day demote: default pending view and pendingReview exclude unreviewed >14d
{
  const fresh = addJob({});
  addJob({ scored_at: iso(20) }); // stale
  const def = getAutojobJobs({ status: 'active', hideActioned: true });
  assert.deepEqual(def.jobs.map(j => j.id), [fresh], 'default view = live queue only');
  assert.equal(def.total, 1);
  const stale = getAutojobJobs({ status: 'active', hideActioned: true, includeStale: true });
  assert.equal(stale.total, 2, 'Show stale (>14d) toggle brings the tail back');
  assert.equal(getAutojobStats().pendingReview, 1, 'overview count matches the default view');
}

// 3. Low-confidence rows sort last regardless of score
{
  fixture.prepare('DELETE FROM jobs').run();
  const a = addJob({ fit_score: 7 });            // normal, lower score
  const b = addJob({ fit_score: 8, low_confidence: 1 });
  const c = addJob({ fit_score: 9, low_confidence: 1 });
  const list = getAutojobJobs({ status: 'active', hideActioned: true, includeStale: true, pageSize: 50 });
  assert.deepEqual(list.jobs.map(j => j.id), [a, c, b], 'low_confidence=1 rows sink below all scored order');
}

// 4. Dismiss reason writes to jobs.dismiss_reason; null action rolls the decision back
{
  const id = addJob({});
  setUserAction(id, 'dismissed', 'phone-field');
  const row = fixture.prepare('SELECT user_action, dismiss_reason, user_action_at FROM jobs WHERE id = ?').get(id) as Record<string, string | null>;
  assert.equal(row.user_action, 'dismissed');
  assert.equal(row.dismiss_reason, 'phone-field');
  assert.ok(row.user_action_at);
  const id2 = addJob({});
  setUserAction(id2, 'dismissed'); // no reason — must never block the dismiss
  assert.equal((fixture.prepare('SELECT dismiss_reason FROM jobs WHERE id = ?').get(id2) as { dismiss_reason: string | null }).dismiss_reason, null);
  setUserAction(id, null); // apply rollback path
  const undone = fixture.prepare('SELECT user_action, dismiss_reason FROM jobs WHERE id = ?').get(id) as Record<string, string | null>;
  assert.equal(undone.user_action, null);
  assert.equal(undone.dismiss_reason, null);
}

// 5. Expiry pressure: pending jobs within 3 days of the 30d-posted / 45d-fetched limits
{
  fixture.prepare('DELETE FROM jobs').run();
  addJob({ posted_at: iso(29).slice(0, 10) });                       // counted: hits the 30d posted limit
  addJob({ posted_at: iso(5).slice(0, 10) });                        // not counted
  const noPosted = addJob({ posted_at: null });                      // no posting date → counted via 45d fetched limit
  fixture.prepare('UPDATE jobs SET fetched_at = ? WHERE id = ?').run(iso(44), noPosted);
  addJob({ posted_at: iso(29).slice(0, 10), user_action: 'applied' }); // already decided
  addJob({ posted_at: iso(29).slice(0, 10), status: 'expired' });      // already retired
  assert.equal(getExpiringPendingCount(3), 2);
}

// 6. Tracker: unique posting_url, company upsert on promote
{
  const { createApplication, getOrCreateCompanyByName, getCompanies } = await import('../lib/db');
  const first = createApplication({ company_name: 'Acme Corp', role_title: 'Ops', posting_url: 'https://x/1', status: 'applied' });
  assert.equal(first.status, 'applied');
  assert.throws(() => createApplication({ company_name: 'Acme Corp', role_title: 'Ops again', posting_url: 'https://x/1', status: 'applied' }),
    /UNIQUE constraint failed/, 'a retry must not create a duplicate tracker row');
  createApplication({ company_name: 'Other', role_title: 'X', posting_url: null }); // NULL urls stay unrestricted
  getOrCreateCompanyByName('Acme Corp');
  getOrCreateCompanyByName('ACME CORP'); // upsert matches lowercased name
  const companies = getCompanies();
  assert.equal(companies.length, 1, 'case-different names must upsert into one company row');
  assert.equal(companies[0].name, 'Acme Corp');
}

fs.rmSync(tmp, { recursive: true, force: true });
console.log('dashboard tests: all passed');
}

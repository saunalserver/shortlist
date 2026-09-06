/**
 * Read/write access to the autojob pipeline database (data/autojob.db in the pipeline package).
 * The Python pipeline owns the schema; this file only reads it and writes two things:
 * your decisions (jobs.user_action) and commands for the worker (commands table).
 */
import Database from 'better-sqlite3';

const AUTOJOB_DB_PATH = process.env.AUTOJOB_DB_PATH || '/app/autojob-source/data/autojob.db';

let _db: Database.Database | null = null;

function getDb(): Database.Database {
  if (!_db) {
    _db = new Database(AUTOJOB_DB_PATH);
    _db.pragma('busy_timeout = 10000');
  }
  return _db;
}

export interface AutojobJob {
  id: number;
  url: string;
  title: string | null;
  snippet: string | null;
  description: string | null;
  company: string | null;
  location: string | null;
  source: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  employment_type: string | null;
  posted_at: string | null;
  fit_score: number | null;
  fit_reasoning: string | null;
  strengths: string[] | null;
  gaps: string[] | null;
  skip_reason: string | null;
  prefilter_reason: string | null;
  low_confidence: number | null;
  status: string;
  fetched_at: string;
  processed_at: string | null;
  scored_at: string | null;
  scorer_model: string | null;
  output_folder: string | null;
  docs_generated_at: string | null;
  user_action: 'applied' | 'dismissed' | null;
  user_action_at: string | null;
  run_id: number | null;
  link_checked_at: string | null;
}

type Row = Omit<AutojobJob, 'strengths' | 'gaps'> & { strengths: string | null; gaps: string | null };

export interface AutojobStats {
  totalJobs: number;
  byStatus: Record<string, number>;
  bySource: { source: string; count: number }[];
  avgScore: number | null;
  scoreDistribution: { range: string; count: number }[];
  last7Days: number;
  pendingReview: number;
  shortlisted7Days: number;
  expired: number;
  topCompanies: { company: string; count: number }[];
}

export interface AutojobJobFilters {
  status?: string;
  search?: string;
  minScore?: number;
  source?: string;
  hideActioned?: boolean;
  page?: number;
  pageSize?: number;
  sortBy?: string;
  sortDir?: 'asc' | 'desc';
}

export interface AutojobJobListResult {
  jobs: AutojobJob[];
  total: number;
  page: number;
  pageSize: number;
}

export interface PipelineState {
  status: string;
  current_phase: string | null;
  started_at: string | null;
  jobs_total: number | null;
  jobs_processed: number | null;
  running: boolean;
}

export interface RunRow {
  id: number;
  started_at: string;
  finished_at: string | null;
  dry_run: number;
  status: string;
  fetched: number;
  new_jobs: number;
  prefiltered: number;
  scored: number;
  queued: number;
  skipped: number;
  docs: number;
  errors: number;
  llm_calls: number;
  notes: string | null;
  expired: number | null;
}

export interface SourceHealth {
  source: string;
  last_run: string;
  fetched: number;
  new_jobs: number;
  duration_s: number | null;
  error: string | null;
  total_jobs: number;
  queued_jobs: number;
}

function parseJsonArray(val: string | null): string[] | null {
  if (!val) return null;
  try {
    const parsed = JSON.parse(val);
    return Array.isArray(parsed) ? parsed.map(String) : null;
  } catch {
    return null;
  }
}

function rowToJob(row: Row): AutojobJob {
  return { ...row, strengths: parseJsonArray(row.strengths), gaps: parseJsonArray(row.gaps) };
}

export function getAutojobStats(): AutojobStats {
  const db = getDb();
  const total = db.prepare('SELECT COUNT(*) as count FROM jobs').get() as { count: number };
  const byStatus: Record<string, number> = {};
  for (const r of db.prepare('SELECT status, COUNT(*) as count FROM jobs GROUP BY status').all() as { status: string; count: number }[]) {
    byStatus[r.status] = r.count;
  }
  const bySource = db.prepare(
    "SELECT COALESCE(source, 'unknown') as source, COUNT(*) as count FROM jobs GROUP BY source ORDER BY count DESC"
  ).all() as { source: string; count: number }[];
  const avg = db.prepare('SELECT AVG(fit_score) as avg FROM jobs WHERE fit_score IS NOT NULL').get() as { avg: number | null };
  const ranges = [
    { range: '1-2', min: 1, max: 3 }, { range: '3-4', min: 3, max: 5 }, { range: '5', min: 5, max: 6 },
    { range: '6-7', min: 6, max: 8 }, { range: '8-10', min: 8, max: 11 },
  ];
  const scoreDistribution = ranges.map(({ range, min, max }) => ({
    range,
    count: (db.prepare('SELECT COUNT(*) as c FROM jobs WHERE fit_score >= ? AND fit_score < ?').get(min, max) as { c: number }).c,
  }));
  const weekAgo = new Date(Date.now() - 7 * 86400_000).toISOString();
  const last7 = db.prepare('SELECT COUNT(*) as c FROM jobs WHERE fetched_at >= ?').get(weekAgo) as { c: number };
  const pending = db.prepare(
    "SELECT COUNT(*) as c FROM jobs WHERE status IN ('queued','docs_generated') AND user_action IS NULL"
  ).get() as { c: number };
  const shortlisted7 = db.prepare(
    "SELECT COUNT(*) as c FROM jobs WHERE status IN ('queued','docs_generated','expired') AND scored_at >= ? AND fit_score >= 6"
  ).get(weekAgo) as { c: number };
  const expired = db.prepare("SELECT COUNT(*) as c FROM jobs WHERE status = 'expired'").get() as { c: number };
  const topCompanies = db.prepare(
    "SELECT company, COUNT(*) as count FROM jobs WHERE company IS NOT NULL AND company NOT IN ('', 'Unknown') AND status IN ('queued','docs_generated') GROUP BY company ORDER BY count DESC LIMIT 10"
  ).all() as { company: string; count: number }[];
  return {
    totalJobs: total.count,
    byStatus,
    bySource,
    avgScore: avg.avg !== null ? Math.round(avg.avg * 10) / 10 : null,
    scoreDistribution,
    last7Days: last7.c,
    pendingReview: pending.c,
    shortlisted7Days: shortlisted7.c,
    expired: expired.c,
    topCompanies,
  };
}

const SORTABLE = new Set(['fetched_at', 'fit_score', 'title', 'company', 'status', 'scored_at', 'source', 'posted_at']);

export function getAutojobJobs(filters: AutojobJobFilters = {}): AutojobJobListResult {
  const db = getDb();
  const { status, search, minScore, source, hideActioned = true, page = 1, pageSize = 25, sortBy = 'fit_score', sortDir = 'desc' } = filters;
  const where: string[] = ['1=1'];
  const params: (string | number)[] = [];
  if (status === 'active') {
    where.push("status IN ('queued','docs_generated')");
  } else if (status) {
    where.push('status = ?');
    params.push(status);
  }
  if (hideActioned) where.push('user_action IS NULL');
  if (search) {
    where.push('(title LIKE ? OR company LIKE ? OR location LIKE ?)');
    params.push(`%${search}%`, `%${search}%`, `%${search}%`);
  }
  if (minScore !== undefined) {
    where.push('fit_score >= ?');
    params.push(minScore);
  }
  if (source) {
    where.push('source = ?');
    params.push(source);
  }
  const whereSql = where.join(' AND ');
  const sortCol = SORTABLE.has(sortBy) ? sortBy : 'fit_score';
  const dir = sortDir === 'asc' ? 'ASC' : 'DESC';
  const total = (db.prepare(`SELECT COUNT(*) as c FROM jobs WHERE ${whereSql}`).get(...params) as { c: number }).c;
  const rows = db.prepare(
    `SELECT * FROM jobs WHERE ${whereSql} ORDER BY ${sortCol} ${dir} NULLS LAST, fetched_at DESC LIMIT ? OFFSET ?`
  ).all(...params, pageSize, (page - 1) * pageSize) as Row[];
  return { jobs: rows.map(rowToJob), total, page, pageSize };
}

export function getAutojobJobById(id: number): AutojobJob | null {
  const row = getDb().prepare('SELECT * FROM jobs WHERE id = ?').get(id) as Row | undefined;
  return row ? rowToJob(row) : null;
}

export function getActionedIds(): Set<number> {
  const rows = getDb().prepare('SELECT id FROM jobs WHERE user_action IS NOT NULL').all() as { id: number }[];
  return new Set(rows.map(r => r.id));
}

export function setUserAction(id: number, action: 'applied' | 'dismissed'): void {
  getDb().prepare('UPDATE jobs SET user_action = ?, user_action_at = ? WHERE id = ?').run(action, new Date().toISOString(), id);
}

export function getPipelineState(): PipelineState {
  const row = getDb().prepare('SELECT * FROM pipeline_state WHERE id = 1').get() as Partial<PipelineState> | undefined;
  let status = row?.status ?? 'idle';
  // A run that died without cleaning up would otherwise look "running" forever (runs never take 4 h).
  const started = row?.started_at ? new Date(row.started_at).getTime() : 0;
  if (status === 'running' && started && Date.now() - started > 4 * 3600_000) status = 'idle';
  return {
    status,
    current_phase: row?.current_phase ?? null,
    started_at: row?.started_at ?? null,
    jobs_total: row?.jobs_total ?? null,
    jobs_processed: row?.jobs_processed ?? null,
    running: status === 'running',
  };
}

export function enqueueCommand(command: 'run' | 'docs' | 'abort', arg?: string): number {
  const res = getDb().prepare('INSERT INTO commands (command, arg, created_at) VALUES (?, ?, ?)')
    .run(command, arg ?? null, new Date().toISOString());
  return Number(res.lastInsertRowid);
}

/** Abort must bypass the queue: the worker is busy inside the run and only checks this flag between jobs. */
export function setAbortFlag(): void {
  getDb().prepare("UPDATE pipeline_state SET command = 'abort' WHERE id = 1").run();
}

export function getPendingCommands(): { id: number; command: string; arg: string | null; status: string; created_at: string }[] {
  return getDb().prepare(
    "SELECT id, command, arg, status, created_at FROM commands WHERE status IN ('pending','running') ORDER BY id"
  ).all() as { id: number; command: string; arg: string | null; status: string; created_at: string }[];
}

export function getRecentRuns(limit = 10): RunRow[] {
  return getDb().prepare('SELECT * FROM runs ORDER BY id DESC LIMIT ?').all(limit) as RunRow[];
}

export interface SerperCredits {
  used: number;
  total: number;
  left: number;
}

/** Serper has no balance API — the pipeline counts its own spend in the meta table. */
export function getSerperCredits(): SerperCredits {
  let used = 0;
  try {
    const row = getDb().prepare("SELECT value FROM meta WHERE key = 'serper_credits_used'").get() as { value: string } | undefined;
    used = row ? Number(row.value) || 0 : 0;
  } catch {
    // meta table not created yet
  }
  let total = 2500;
  try {
    const fs = require('fs');
    const env = fs.readFileSync(`${process.env.AUTOJOB_PROJECT_ROOT || '/app/autojob-source'}/.env`, 'utf8');
    const m = env.match(/^SERPER_CREDITS_TOTAL=(\d+)/m);
    if (m) total = Number(m[1]);
  } catch {
    // keep default
  }
  return { used, total, left: Math.max(total - used, 0) };
}

export function getSourceHealth(): SourceHealth[] {
  return getDb().prepare(`
    SELECT s.source, s.started_at as last_run, s.fetched, s.new_jobs, s.duration_s, s.error,
           (SELECT COUNT(*) FROM jobs j WHERE j.source = s.source) as total_jobs,
           (SELECT COUNT(*) FROM jobs j WHERE j.source = s.source AND j.status IN ('queued','docs_generated')) as queued_jobs
    FROM source_runs s
    WHERE s.id IN (SELECT MAX(id) FROM source_runs GROUP BY source)
    ORDER BY s.new_jobs DESC, s.source
  `).all() as SourceHealth[];
}

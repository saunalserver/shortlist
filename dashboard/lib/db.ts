import Database from 'better-sqlite3';
import path from 'path';
import fs from 'fs';
import { Application, Company, DashboardStats, ApplicationFilters, CreateApplicationInput, UpdateApplicationInput, CreateCompanyInput, UpdateCompanyInput } from './types';
import { generateId } from './utils';
import { STATUSES, ACTIVE_STATUSES } from './constants';

const DB_PATH = process.env.DATABASE_PATH || path.join(process.cwd(), 'data', 'jobsearch.db');

let _db: Database.Database | null = null;

function getDb(): Database.Database {
  if (!_db) {
    const dataDir = path.dirname(DB_PATH);
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }
    _db = new Database(DB_PATH);
    _db.exec(`
  CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    role_title TEXT NOT NULL,
    date_applied DATE,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'bookmarked',
    posting_url TEXT,
    salary_info TEXT,
    location TEXT,
    notes TEXT,
    tags TEXT DEFAULT '[]',
    next_action TEXT,
    next_action_date DATE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    website TEXT,
    size TEXT,
    industry TEXT,
    notes TEXT,
    watchlist INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );


  CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
  CREATE INDEX IF NOT EXISTS idx_applications_date ON applications(date_applied);


`);

  }
  return _db;
}

// Helper to parse tags
function parseTags(tags: string | null): string[] {
  if (!tags) return [];
  try {
    return JSON.parse(tags);
  } catch {
    return [];
  }
}

// ============ APPLICATIONS ============

export function getApplications(filters?: ApplicationFilters): Application[] {
  let sql = 'SELECT * FROM applications WHERE 1=1';
  const params: (string | null)[] = [];

  if (filters?.status) {
    sql += ' AND status = ?';
    params.push(filters.status);
  }

  if (filters?.source) {
    sql += ' AND source = ?';
    params.push(filters.source);
  }

  if (filters?.search) {
    sql += ' AND (company_name LIKE ? OR role_title LIKE ?)';
    const searchTerm = `%${filters.search}%`;
    params.push(searchTerm, searchTerm);
  }

  sql += ' ORDER BY updated_at DESC';

  const rows = getDb().prepare(sql).all(...params) as Record<string, unknown>[];

  return rows.map((row) => ({
    ...row,
    tags: parseTags(row.tags as string | null),
  })) as Application[];
}

export function getApplicationById(id: string): Application | null {
  const row = getDb().prepare('SELECT * FROM applications WHERE id = ?').get(id) as Record<string, unknown> | undefined;

  if (!row) return null;

  return {
    ...row,
    tags: parseTags(row.tags as string | null),
  } as Application;
}

export function createApplication(input: CreateApplicationInput): Application {
  const id = generateId();
  const now = new Date().toISOString();

  const stmt = getDb().prepare(`
    INSERT INTO applications (
      id, company_name, role_title, date_applied, source, status,
      posting_url, salary_info, location, notes, tags,
      next_action, next_action_date, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  stmt.run(
    id,
    input.company_name,
    input.role_title,
    input.date_applied ?? null,
    input.source ?? null,
    input.status ?? 'bookmarked',
    input.posting_url ?? null,
    input.salary_info ?? null,
    input.location ?? null,
    input.notes ?? null,
    JSON.stringify(input.tags ?? []),
    input.next_action ?? null,
    input.next_action_date ?? null,
    now,
    now
  );

  return getApplicationById(id)!;
}

export function updateApplication(id: string, input: UpdateApplicationInput): Application | null {
  const existing = getApplicationById(id);
  if (!existing) return null;

  const updates: string[] = [];
  const values: (string | null)[] = [];

  const fields = [
    'company_name', 'role_title', 'date_applied', 'source', 'status',
    'posting_url', 'salary_info', 'location', 'notes', 'tags',
    'next_action', 'next_action_date'
  ] as const;

  for (const field of fields) {
    if (field in input && (input as Record<string, unknown>)[field] !== undefined) {
      updates.push(`${field} = ?`);
      if (field === 'tags') {
        values.push(JSON.stringify((input as Record<string, unknown>).tags ?? []));
      } else {
        values.push((input as Record<string, unknown>)[field] as string | null);
      }
    }
  }

  if (updates.length === 0) return existing;

  updates.push('updated_at = ?');
  values.push(new Date().toISOString());
  values.push(id);

  getDb().prepare(`UPDATE applications SET ${updates.join(', ')} WHERE id = ?`).run(...values);

  return getApplicationById(id);
}

export function deleteApplication(id: string): boolean {
  const result = getDb().prepare('DELETE FROM applications WHERE id = ?').run(id);
  return result.changes > 0;
}

// ============ STATS ============

export function getStats(): DashboardStats {
  // Total applications
  const total = getDb().prepare('SELECT COUNT(*) as count FROM applications').get() as { count: number };

  // Active pipeline (non-terminal statuses)
  const active = getDb().prepare(`
    SELECT COUNT(*) as count FROM applications
    WHERE status IN (${ACTIVE_STATUSES.map(() => '?').join(',')})
  `).get(...ACTIVE_STATUSES) as { count: number };

  // This week
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 7);
  const thisWeek = getDb().prepare(`
    SELECT COUNT(*) as count FROM applications
    WHERE created_at >= ?
  `).get(weekAgo.toISOString()) as { count: number };

  // Response rate (screening+ / applied+)
  const responseCount = getDb().prepare(`
    SELECT COUNT(*) as count FROM applications
    WHERE status IN ('screening', 'interview', 'final_round', 'offer', 'accepted')
  `).get() as { count: number };

  const appliedCount = getDb().prepare(`
    SELECT COUNT(*) as count FROM applications
    WHERE status != 'bookmarked'
  `).get() as { count: number };

  const responseRate = appliedCount.count > 0
    ? Math.round((responseCount.count / appliedCount.count) * 100)
    : 0;

  // By status
  const statusRows = getDb().prepare(`
    SELECT status, COUNT(*) as count FROM applications
    GROUP BY status
  `).all() as { status: string; count: number }[];

  const byStatus: Record<string, number> = {};
  for (const status of STATUSES) {
    byStatus[status] = 0;
  }
  for (const row of statusRows) {
    byStatus[row.status] = row.count;
  }

  // Weekly applications (last 8 weeks)
  const weeklyApplications: { week: string; count: number }[] = [];
  for (let i = 7; i >= 0; i--) {
    const weekStart = new Date();
    weekStart.setDate(weekStart.getDate() - (i * 7));
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 7);

    const count = getDb().prepare(`
      SELECT COUNT(*) as count FROM applications
      WHERE created_at >= ? AND created_at < ?
    `).get(weekStart.toISOString(), weekEnd.toISOString()) as { count: number };

    weeklyApplications.push({
      week: weekStart.toISOString().split('T')[0],
      count: count.count,
    });
  }

  return {
    totalApplications: total.count,
    activePipeline: active.count,
    thisWeek: thisWeek.count,
    responseRate,
    byStatus: byStatus as DashboardStats['byStatus'],
    weeklyApplications,
  };
}

// ============ COMPANIES ============

export function getCompanies(): Company[] {
  return getDb().prepare('SELECT * FROM companies ORDER BY name').all() as Company[];
}

export function getCompanyById(id: string): Company | null {
  const row = getDb().prepare('SELECT * FROM companies WHERE id = ?').get(id);
  return row ? { ...row, watchlist: Boolean((row as { watchlist: number }).watchlist) } as Company : null;
}

export function createCompany(input: CreateCompanyInput): Company {
  const id = generateId();

  getDb().prepare(`
    INSERT INTO companies (id, name, website, size, industry, notes, watchlist, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    id,
    input.name,
    input.website ?? null,
    input.size ?? null,
    input.industry ?? null,
    input.notes ?? null,
    input.watchlist ? 1 : 0,
    new Date().toISOString()
  );

  return getCompanyById(id)!;
}

export function updateCompany(id: string, input: UpdateCompanyInput): Company | null {
  const existing = getCompanyById(id);
  if (!existing) return null;

  const updates: string[] = [];
  const values: (string | number | null)[] = [];

  const fields = ['name', 'website', 'size', 'industry', 'notes', 'watchlist'] as const;

  for (const field of fields) {
    if (field in input && (input as Record<string, unknown>)[field] !== undefined) {
      updates.push(`${field} = ?`);
      if (field === 'watchlist') {
        values.push((input as Record<string, unknown>).watchlist ? 1 : 0);
      } else {
        values.push((input as Record<string, unknown>)[field] as string | null);
      }
    }
  }

  if (updates.length === 0) return existing;

  values.push(id);

  getDb().prepare(`UPDATE companies SET ${updates.join(', ')} WHERE id = ?`).run(...values);

  return getCompanyById(id);
}

export function deleteCompany(id: string): boolean {
  const result = getDb().prepare('DELETE FROM companies WHERE id = ?').run(id);
  return result.changes > 0;
}

export function getOrCreateCompanyByName(name: string): Company {
  const trimmed = name.trim();
  const existing = getDb().prepare("SELECT * FROM companies WHERE LOWER(name) = LOWER(?)").get(trimmed) as Record<string, unknown> | undefined;
  if (existing) {
    return { ...existing, watchlist: Boolean(existing.watchlist) } as Company;
  }
  return createCompany({ name: trimmed });
}

// ============ EXPORT ============

export function exportAllApplications(): Application[] {
  return getApplications();
}

export function exportAllCompanies(): Company[] {
  return getCompanies();
}

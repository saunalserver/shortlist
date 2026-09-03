/**
 * check-reminders.ts
 *
 * Standalone script that queries the Command Center SQLite DB for stale
 * job applications and sends Telegram follow-up reminders.
 *
 * Rules:
 *   - 'applied'  for 14+ days with no status change -> nudge
 *   - 'screening' for 7+ days with no status change -> nudge
 *   - at most one nudge per application every 14 days; nothing after 60 days stale
 *
 * Idempotent: a JSON file tracks when each application was last reminded.
 *
 * Usage:
 *   npx tsx scripts/check-reminders.ts
 *
 * Environment variables (loaded from the pipeline .env):
 *   TELEGRAM_BOT_TOKEN
 *   TELEGRAM_CHAT_ID
 *   DATABASE_PATH  (optional, defaults to data/jobsearch.db relative to project root)
 */

import Database from 'better-sqlite3';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, '..');
const DB_PATH = process.env.DATABASE_PATH || path.join(PROJECT_ROOT, 'data', 'jobsearch.db');
const REMINDERS_FILE = path.join(PROJECT_ROOT, 'data', 'reminders-sent.json');
const AUTOJOB_ENV_PATH = path.resolve(PROJECT_ROOT, '..', 'pipeline', '.env');

// ---------------------------------------------------------------------------
// Load .env manually (no dotenv dependency needed)
// ---------------------------------------------------------------------------

function loadEnv(filePath: string): void {
  if (!fs.existsSync(filePath)) {
    console.error(`[reminders] .env file not found at ${filePath}`);
    process.exit(1);
  }
  const content = fs.readFileSync(filePath, 'utf-8');
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIndex = trimmed.indexOf('=');
    if (eqIndex === -1) continue;
    const key = trimmed.slice(0, eqIndex).trim();
    const value = trimmed.slice(eqIndex + 1).trim();
    // Only set if not already defined in environment
    if (process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
}

loadEnv(AUTOJOB_ENV_PATH);

const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID;

if (!TELEGRAM_BOT_TOKEN || !TELEGRAM_CHAT_ID) {
  console.error('[reminders] TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.');
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StaleApplication {
  id: string;
  company_name: string;
  role_title: string;
  status: string;
  posting_url: string | null;
  next_action: string | null;
  updated_at: string;
  days_stale: number;
}

type RemindersSent = Record<string, string>; // applicationId -> ISO date string (YYYY-MM-DD)

// ---------------------------------------------------------------------------
// Reminder state (JSON file)
// ---------------------------------------------------------------------------

function loadReminders(): RemindersSent {
  if (!fs.existsSync(REMINDERS_FILE)) return {};
  try {
    return JSON.parse(fs.readFileSync(REMINDERS_FILE, 'utf-8'));
  } catch {
    return {};
  }
}

function saveReminders(reminders: RemindersSent): void {
  const dir = path.dirname(REMINDERS_FILE);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(REMINDERS_FILE, JSON.stringify(reminders, null, 2) + '\n');
}

// ---------------------------------------------------------------------------
// Query stale applications
// ---------------------------------------------------------------------------

function getStaleApplications(db: Database.Database): StaleApplication[] {
  const rows = db.prepare(`
    SELECT
      id,
      company_name,
      role_title,
      status,
      posting_url,
      next_action,
      updated_at,
      CAST(julianday('now') - julianday(updated_at) AS INTEGER) AS days_stale
    FROM applications
    WHERE
      (status = 'applied' AND julianday('now') - julianday(updated_at) >= 14)
      OR
      (status = 'screening' AND julianday('now') - julianday(updated_at) >= 7)
    ORDER BY days_stale DESC
  `).all() as StaleApplication[];

  return rows;
}

// ---------------------------------------------------------------------------
// Telegram API (with retry on 429)
// ---------------------------------------------------------------------------

async function sendTelegramMessage(
  text: string,
  maxRetries: number = 3,
): Promise<boolean> {
  const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: TELEGRAM_CHAT_ID,
          text,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        }),
      });

      if (response.ok) {
        return true;
      }

      if (response.status === 429) {
        const body = (await response.json()) as { parameters?: { retry_after?: number } };
        const retryAfter = body.parameters?.retry_after ?? 30;
        console.warn(
          `[reminders] Rate limited by Telegram. Waiting ${retryAfter + 1}s (attempt ${attempt}/${maxRetries})`,
        );
        await sleep((retryAfter + 1) * 1000);
        continue;
      }

      const body = await response.text();
      console.error(
        `[reminders] Telegram API error ${response.status}: ${body} (attempt ${attempt}/${maxRetries})`,
      );
      return false;
    } catch (err) {
      console.error(
        `[reminders] Network error sending Telegram message (attempt ${attempt}/${maxRetries}):`,
        err,
      );
      if (attempt < maxRetries) {
        await sleep(5000);
      }
    }
  }

  return false;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Build message text
// ---------------------------------------------------------------------------

function buildMessage(app: StaleApplication): string {
  const actionLine = app.next_action
    ? app.next_action
    : 'No next action set.';

  const postingLine = app.posting_url
    ? `<a href="${app.posting_url}">View posting</a>`
    : '';

  return [
    '⏰ <b>Follow-up reminder</b>',
    '',
    `<b>${escapeHtml(app.role_title)}</b> at <b>${escapeHtml(app.company_name)}</b>`,
    `Status: ${app.status} for ${app.days_stale} days`,
    '',
    actionLine,
    '',
    postingLine,
  ]
    .filter(Boolean)
    .join('\n');
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  console.log(`[reminders] Starting reminder check at ${new Date().toISOString()}`);
  console.log(`[reminders] Database: ${DB_PATH}`);

  if (!fs.existsSync(DB_PATH)) {
    console.error(`[reminders] Database not found at ${DB_PATH}`);
    process.exit(1);
  }

  const db = new Database(DB_PATH, { readonly: true });

  const staleApps = getStaleApplications(db);
  console.log(`[reminders] Found ${staleApps.length} stale application(s).`);

  db.close();

  if (staleApps.length === 0) {
    console.log('[reminders] Nothing to remind about. Done.');
    return;
  }

  const reminders = loadReminders();
  const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
  let sent = 0;
  let skipped = 0;

  for (const app of staleApps) {
    // Stop nagging about very old applications — assume ghosted.
    if (app.days_stale > 60) {
      skipped++;
      continue;
    }
    // Remind at most once every 14 days per application.
    const last = reminders[app.id];
    if (last && (new Date(today).getTime() - new Date(last).getTime()) / 86400000 < 14) {
      skipped++;
      continue;
    }

    const message = buildMessage(app);
    console.log(
      `[reminders] Sending reminder for: ${app.role_title} at ${app.company_name} (${app.status}, ${app.days_stale} days stale)`,
    );

    const ok = await sendTelegramMessage(message);

    if (ok) {
      reminders[app.id] = today;
      sent++;
      // Small delay between messages to avoid hitting rate limits
      await sleep(500);
    } else {
      console.error(
        `[reminders] Failed to send reminder for application ${app.id}`,
      );
    }
  }

  saveReminders(reminders);

  console.log(
    `[reminders] Done. Sent: ${sent}, Skipped (recently reminded or >60 days): ${skipped}, Total stale: ${staleApps.length}`,
  );
}

main().catch((err) => {
  console.error('[reminders] Fatal error:', err);
  process.exit(1);
});

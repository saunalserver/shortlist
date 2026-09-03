import fs from 'fs';
import path from 'path';

const AUTOJOB_PROJECT_ROOT = process.env.AUTOJOB_PROJECT_ROOT || '/app/autojob-source';

export function readAutojobLogs(lines: number = 100): string[] {
  const logPath = path.join(AUTOJOB_PROJECT_ROOT, 'data', 'autojob.log');
  try {
    const content = fs.readFileSync(logPath, 'utf-8');
    return content.split('\n').filter(l => l.trim()).slice(-lines);
  } catch {
    return [`[ERROR] Could not read log file at: ${logPath}`];
  }
}

/** Raw text of config/search.yaml — shown read-only; edit it in the repo (or ask your agent to). */
export function readSearchConfig(): string {
  const p = path.join(AUTOJOB_PROJECT_ROOT, 'config', 'search.yaml');
  try {
    return fs.readFileSync(p, 'utf-8');
  } catch {
    return `# could not read ${p}`;
  }
}

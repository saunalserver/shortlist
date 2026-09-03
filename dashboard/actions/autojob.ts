'use server';

import {
  getAutojobStats, getAutojobJobs, getAutojobJobById, getPipelineState, enqueueCommand, getPendingCommands, setAbortFlag,
  setUserAction, getActionedIds, getRecentRuns, getSourceHealth,
  type AutojobJobFilters, type AutojobJob, type AutojobStats, type AutojobJobListResult, type PipelineState,
  type RunRow, type SourceHealth,
} from '@/lib/autojob-db';
import { readAutojobLogs, readSearchConfig } from '@/lib/autojob-config';
import { createApplication } from '@/lib/db';

export async function fetchAutojobStats(): Promise<AutojobStats> {
  return getAutojobStats();
}

export async function fetchAutojobJobs(filters: AutojobJobFilters): Promise<AutojobJobListResult> {
  return getAutojobJobs(filters);
}

export async function fetchAutojobJob(id: number): Promise<AutojobJob | null> {
  return getAutojobJobById(id);
}

export async function fetchActionedJobIds(): Promise<Set<number>> {
  return getActionedIds();
}

export async function fetchPipelineState(): Promise<PipelineState> {
  return getPipelineState();
}

export async function fetchRecentRuns(limit = 10): Promise<RunRow[]> {
  return getRecentRuns(limit);
}

export async function fetchSourceHealth(): Promise<SourceHealth[]> {
  return getSourceHealth();
}

export async function fetchSearchConfig(): Promise<string> {
  return readSearchConfig();
}

export async function fetchAutojobLogs(lines: number = 100): Promise<string[]> {
  return readAutojobLogs(lines);
}

export async function fetchPendingCommands() {
  return getPendingCommands();
}

/** Ask the host-side worker to start a run (the dashboard container has no Python). */
export async function triggerAutojobRun(dryRun: boolean = false): Promise<{ success: boolean; message: string }> {
  if (getPipelineState().running) return { success: false, message: 'Pipeline is already running' };
  if (getPendingCommands().some(c => c.command === 'run')) return { success: false, message: 'A run is already queued' };
  enqueueCommand('run', dryRun ? 'dry' : undefined);
  return { success: true, message: dryRun ? 'Dry run queued — the worker picks it up within a few seconds' : 'Run queued — the worker picks it up within a few seconds' };
}

export async function abortPipeline(): Promise<{ success: boolean; message: string }> {
  if (!getPipelineState().running) return { success: false, message: 'Pipeline is not running' };
  setAbortFlag();
  return { success: true, message: 'Abort requested — the run stops after the current job' };
}

export async function requestDocs(jobId: number): Promise<{ success: boolean; message: string }> {
  const job = getAutojobJobById(jobId);
  if (!job) return { success: false, message: 'Job not found' };
  if (getPendingCommands().some(c => c.command === 'docs' && c.arg === String(jobId))) {
    return { success: false, message: 'Documents are already being generated for this job' };
  }
  enqueueCommand('docs', String(jobId));
  return { success: true, message: 'Generating resume + cover letter (1–3 minutes). Reopen the job to see the PDFs.' };
}

export async function promoteJobToTracker(jobId: number): Promise<{ success: boolean; message: string }> {
  const job = getAutojobJobById(jobId);
  if (!job) return { success: false, message: 'Job not found' };
  try {
    const application = createApplication({
      company_name: job.company || 'Unknown',
      role_title: job.title || 'Untitled Role',
      posting_url: job.url,
      location: job.location,
      status: 'applied',
      date_applied: new Date().toISOString().split('T')[0],
      notes: job.fit_reasoning ? `Autojob (score ${job.fit_score}/10). ${job.fit_reasoning}` : `Autojob (score ${job.fit_score}/10)`,
      source: 'other',
      tags: ['autojob', ...(job.source ? [job.source] : [])],
    });
    setUserAction(jobId, 'applied');
    return { success: true, message: `Added to tracker as Applied: ${application.role_title}` };
  } catch (error: unknown) {
    return { success: false, message: `Failed to create application: ${(error as Error).message}` };
  }
}

export async function dismissPipelineJob(jobId: number): Promise<{ success: boolean; message: string }> {
  try {
    setUserAction(jobId, 'dismissed');
    return { success: true, message: 'Dismissed' };
  } catch (error: unknown) {
    return { success: false, message: `Failed: ${(error as Error).message}` };
  }
}

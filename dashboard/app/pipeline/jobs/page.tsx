'use client';

import { useState, useEffect, useCallback } from 'react';
import { fetchAutojobJobs, fetchAutojobJob, promoteJobToTracker, dismissPipelineJob, fetchActionedJobIds, requestDocs, fetchExpiringPendingCount } from '@/actions/autojob';
import type { AutojobJob, AutojobJobFilters } from '@/lib/autojob-db';
import { DISMISS_REASONS } from '@/lib/constants';

const STATUSES = ['queued', 'docs_generated', 'expired', 'new', 'skipped', 'prefiltered', 'error'];

/** score_facts is JSON or NULL (populated once scoring v2 lands); render only scalar entries, defensively. */
function parseScoreFacts(val: string | null): [string, string][] | null {
  if (!val) return null;
  try {
    const obj: unknown = JSON.parse(val);
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
      return Object.entries(obj as Record<string, unknown>)
        .filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object')
        .map(([k, v]) => [k, String(v)] as [string, string]);
    }
  } catch {
    // not valid JSON — nothing to show
  }
  return null;
}

/** "3 d" / "5 w" / "—" for a YYYY-MM-DD date. */
function age(date: string | null): string {
  if (!date) return '—';
  const days = Math.floor((Date.now() - new Date(date.slice(0, 10) + 'T12:00:00Z').getTime()) / 86400_000);
  if (days < 0) return 'today';
  if (days === 0) return 'today';
  if (days < 14) return `${days} d`;
  return `${Math.round(days / 7)} w`;
}

function scoreColor(score: number | null): string {
  if (score === null) return 'bg-[#1a2744] text-[#5a6f8a]';
  if (score >= 8) return 'bg-green-900/50 text-green-400';
  if (score >= 6) return 'bg-[rgba(232,163,23,0.2)] text-[#e8a317]';
  if (score >= 4) return 'bg-yellow-900/30 text-yellow-500';
  return 'bg-red-900/30 text-red-400';
}

function statusColor(status: string): string {
  switch (status) {
    case 'new': return 'bg-blue-900/40 text-blue-400';
    case 'queued': return 'bg-yellow-900/40 text-yellow-400';
    case 'docs_generated': return 'bg-green-900/40 text-green-400';
    case 'expired': return 'bg-gray-800 text-gray-400 line-through';
    case 'skipped': return 'bg-gray-800 text-gray-500';
    case 'prefiltered': return 'bg-gray-900 text-gray-600';
    case 'error': return 'bg-red-900/40 text-red-400';
    default: return 'bg-[#1a2744] text-[#5a6f8a]';
  }
}

export default function PipelineJobsPage() {
  const [jobs, setJobs] = useState<AutojobJob[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');
  const [scoreFilter, setScoreFilter] = useState('');
  const [selectedJob, setSelectedJob] = useState<AutojobJob | null>(null);
  const [panelLoading, setPanelLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState('');
  const [actioning, setActioning] = useState(false);
  const [actionedIds, setActionedIds] = useState<Set<number>>(new Set());
  const [showActioned, setShowActioned] = useState(false);
  const [showStale, setShowStale] = useState(false);
  const [sortBy, setSortBy] = useState<'fit_score' | 'posted_at' | 'scored_at'>('fit_score');
  const [selectedIdx, setSelectedIdx] = useState(-1);
  const [dismissArmed, setDismissArmed] = useState(false);
  const [expiringSoon, setExpiringSoon] = useState(0);

  const pageSize = 25;

  const loadJobs = useCallback(async (): Promise<AutojobJob[]> => {
    setLoading(true);
    const filters: AutojobJobFilters = { page, pageSize, hideActioned: !showActioned, includeStale: showStale, sortBy, sortDir: 'desc' };
    if (search) filters.search = search;
    if (statusFilter) filters.status = statusFilter;
    if (scoreFilter) {
      filters.minScore = parseInt(scoreFilter, 10);
    }
    const result = await fetchAutojobJobs(filters);
    setJobs(result.jobs);
    setTotal(result.total);
    setLoading(false);
    return result.jobs;
  }, [page, search, statusFilter, scoreFilter, showActioned, showStale, sortBy]);

  const loadActioned = useCallback(async () => {
    const ids = await fetchActionedJobIds();
    setActionedIds(ids);
  }, []);

  useEffect(() => { loadJobs(); loadActioned(); }, [loadJobs, loadActioned]);

  useEffect(() => { fetchExpiringPendingCount().then(setExpiringSoon).catch(() => setExpiringSoon(0)); }, []);

  const openJob = useCallback(async (id: number) => {
    setPanelLoading(true);
    setActionMsg('');
    setDismissArmed(false);
    const job = await fetchAutojobJob(id);
    setSelectedJob(job);
    setPanelLoading(false);
  }, []);

  /** After an action, jump to the next still-pending row and open it — the 5-click loop becomes one keypress. */
  const openNextPending = useCallback(async (freshJobs: AutojobJob[], actedId: number) => {
    for (let i = Math.max(selectedIdx, 0); i < freshJobs.length; i++) {
      const job = freshJobs[i];
      if (!job || job.id === actedId || job.user_action) continue;
      setSelectedIdx(i);
      await openJob(job.id);
      return;
    }
    setSelectedJob(null); // nothing pending left on this page
  }, [selectedIdx, openJob]);

  const handleApply = useCallback(async () => {
    if (!selectedJob || actioning) return;
    setActioning(true);
    const actedId = selectedJob.id;
    try {
      const result = await promoteJobToTracker(actedId);
      setActionMsg(result.message);
      if (result.success) {
        setActionedIds(prev => new Set(prev).add(actedId));
        await openNextPending(await loadJobs(), actedId);
      }
    } catch (error: unknown) {
      setActionMsg(`Apply failed: ${(error as Error).message}`);
    } finally {
      setActioning(false);
    }
  }, [selectedJob, actioning, loadJobs, openNextPending]);

  const handleDismiss = useCallback(async (reason: string | null = null) => {
    if (!selectedJob || actioning) return;
    setDismissArmed(false);
    setActioning(true);
    const actedId = selectedJob.id;
    try {
      const result = await dismissPipelineJob(actedId, reason);
      setActionMsg(result.message);
      if (result.success) {
        setActionedIds(prev => new Set(prev).add(actedId));
        await openNextPending(await loadJobs(), actedId);
      }
    } catch (error: unknown) {
      setActionMsg(`Dismiss failed: ${(error as Error).message}`);
    } finally {
      setActioning(false);
    }
  }, [selectedJob, actioning, loadJobs, openNextPending]);

  const handleDocs = useCallback(async () => {
    if (!selectedJob) return;
    setActioning(true);
    try {
      const result = await requestDocs(selectedJob.id);
      setActionMsg(result.message);
    } catch (error: unknown) {
      setActionMsg(`Request failed: ${(error as Error).message}`);
    } finally {
      setActioning(false);
    }
  }, [selectedJob]);

  // Keyboard review: j/k or arrows move through the list, o/Enter opens, a applies, d dismisses
  // (second d or Esc confirms without a reason), 1-7 pick a dismiss reason while the chip row is open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
      if (t && (t.tagName === 'BUTTON' || t.tagName === 'A') && (e.key === 'Enter' || e.key === ' ')) return; // native activation
      if (dismissArmed) {
        const n = parseInt(e.key, 10);
        if (n >= 1 && n <= DISMISS_REASONS.length) {
          e.preventDefault();
          void handleDismiss(DISMISS_REASONS[n - 1].slug);
          return;
        }
      }
      const actionable = selectedJob && !actionedIds.has(selectedJob.id) && !selectedJob.user_action;
      switch (e.key) {
        case 'j':
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIdx(i => Math.min(i + 1, jobs.length - 1));
          break;
        case 'k':
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIdx(i => Math.max(i - 1, 0));
          break;
        case 'Enter':
        case 'o': {
          const job = jobs[Math.min(selectedIdx, jobs.length - 1)] ?? jobs[0];
          if (job) {
            e.preventDefault();
            void openJob(job.id);
          }
          break;
        }
        case 'a':
          if (actionable && !actioning) {
            e.preventDefault();
            void handleApply();
          }
          break;
        case 'd':
          if (dismissArmed) {
            e.preventDefault();
            void handleDismiss(null);
          } else if (actionable && !actioning) {
            e.preventDefault();
            setDismissArmed(true);
          }
          break;
        case 'Escape':
          if (dismissArmed) {
            e.preventDefault();
            void handleDismiss(null); // reasons are optional — never block the dismiss
          } else if (selectedJob) {
            e.preventDefault();
            setSelectedJob(null);
          }
          break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [jobs, selectedIdx, selectedJob, actioning, actionedIds, dismissArmed, openJob, handleApply, handleDismiss]);

  const totalPages = Math.ceil(total / pageSize);
  const scoreFacts = parseScoreFacts(selectedJob?.score_facts ?? null);

  return (
    <div className="flex h-full flex-col bg-[#060a12]">
      <header className="h-16 border-b border-[#1a2744] flex items-center justify-between px-6">
        <h2 className="text-lg font-semibold text-[#d4dce8]">Pipeline Jobs</h2>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-xs text-[#5a6f8a] cursor-pointer">
            <input
              type="checkbox"
              checked={showStale}
              onChange={(e) => { setShowStale(e.target.checked); setPage(1); }}
              className="accent-[#e8a317]"
            />
            Show stale (&gt;14d)
          </label>
          <label className="flex items-center gap-2 text-xs text-[#5a6f8a] cursor-pointer">
            <input
              type="checkbox"
              checked={showActioned}
              onChange={(e) => { setShowActioned(e.target.checked); setPage(1); }}
              className="accent-[#e8a317]"
            />
            Show actioned
          </label>
          {expiringSoon > 0 && (
            <span className="text-xs text-orange-400" title="Queued, unreviewed, and within 3 days of the 30d-posted / 45d-fetched expiry limits">
              ⏳ {expiringSoon} pending job{expiringSoon !== 1 ? 's' : ''} retire within 3 days
            </span>
          )}
          <span className="text-sm text-[#5a6f8a]">{total} {showActioned ? 'total' : 'pending'}</span>
        </div>
      </header>

      {/* Filters */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-[#1a2744] bg-[#0b1120]">
        <input
          type="text"
          placeholder="Search jobs..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          className="h-9 rounded-md border border-[#1a2744] bg-[#111b2e] px-3 text-sm text-[#d4dce8] placeholder:text-[#5a6f8a] focus:outline-none focus:ring-1 focus:ring-[#e8a317] w-64"
        />
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="h-9 rounded-md border border-[#1a2744] bg-[#111b2e] px-3 text-sm text-[#d4dce8] focus:outline-none focus:ring-1 focus:ring-[#e8a317]"
        >
          <option value="">All Statuses</option>
          <option value="active">To review (queued + docs ready)</option>
          {STATUSES.map(s => (
            <option key={s} value={s}>{s === 'docs_generated' ? 'docs ready' : s.replace(/_/g, ' ')}</option>
          ))}
        </select>
        <select
          value={scoreFilter}
          onChange={(e) => { setScoreFilter(e.target.value); setPage(1); }}
          className="h-9 rounded-md border border-[#1a2744] bg-[#111b2e] px-3 text-sm text-[#d4dce8] focus:outline-none focus:ring-1 focus:ring-[#e8a317]"
        >
          <option value="">Any Score</option>
          {[10, 9, 8, 7, 6, 5, 4, 3, 2, 1].map(n => (
            <option key={n} value={String(n)}>{n}+</option>
          ))}
        </select>
        <select
          value={sortBy}
          onChange={(e) => { setSortBy(e.target.value as 'fit_score' | 'posted_at' | 'scored_at'); setPage(1); }}
          className="h-9 rounded-md border border-[#1a2744] bg-[#111b2e] px-3 text-sm text-[#d4dce8] focus:outline-none focus:ring-1 focus:ring-[#e8a317]"
        >
          <option value="fit_score">Best score first</option>
          <option value="posted_at">Newest posting first</option>
          <option value="scored_at">Most recently scored first</option>
        </select>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-64 text-[#5a6f8a]">Loading...</div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-[#0b1120] border-b border-[#1a2744]">
              <tr>
                <th className="text-left px-6 py-3 text-xs font-medium text-[#5a6f8a] uppercase tracking-wider">Title</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-[#5a6f8a] uppercase tracking-wider">Company</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-[#5a6f8a] uppercase tracking-wider">Location</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-[#5a6f8a] uppercase tracking-wider">Source</th>
                <th className="text-center px-4 py-3 text-xs font-medium text-[#5a6f8a] uppercase tracking-wider">Score</th>
                <th className="text-center px-4 py-3 text-xs font-medium text-[#5a6f8a] uppercase tracking-wider">Status</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-[#5a6f8a] uppercase tracking-wider" title="Posting date given by the source">Posted</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-[#5a6f8a] uppercase tracking-wider">Fetched</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job, index) => {
                const isActioned = actionedIds.has(job.id);
                return (
                  <tr
                    key={job.id}
                    onClick={() => { setSelectedIdx(index); openJob(job.id); }}
                    className={`border-b border-[#1a2744] cursor-pointer transition-colors ${
                      selectedIdx === index ? 'bg-[#111b2e]' :
                      isActioned
                        ? 'opacity-40 hover:opacity-70'
                        : 'hover:bg-[#111b2e]'
                    }`}
                  >
                    <td className="px-6 py-3">
                      <span className="text-sm text-[#d4dce8] line-clamp-1">{job.title || 'Untitled'}</span>
                    </td>
                    <td className="px-6 py-3">
                      <span className="text-sm text-[#d4dce8]">{job.company || 'Unknown'}</span>
                    </td>
                    <td className="px-4 py-3"><span className="text-xs text-[#5a6f8a] line-clamp-1">{job.location || ''}</span></td>
                    <td className="px-4 py-3"><span className="text-xs text-[#5a6f8a]">{job.source || ''}</span></td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex items-center justify-center px-2 py-0.5 rounded text-xs font-mono font-medium ${scoreColor(job.fit_score)}`}>
                        {job.fit_score ?? '-'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${statusColor(job.status)}`}>
                        {job.status.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-[#5a6f8a]" title={job.posted_at || 'no posting date from this source'}>{age(job.posted_at)}</span>
                    </td>
                    <td className="px-6 py-3">
                      <span className="text-xs text-[#5a6f8a]">
                        {job.fetched_at ? new Date(job.fetched_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '-'}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-6 py-12 text-center text-[#5a6f8a]">
                    {showActioned ? 'No jobs found' : 'All caught up — no pending jobs'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between px-6 py-3 border-t border-[#1a2744] bg-[#0b1120]">
        <span className="text-xs text-[#5a6f8a]">
          Page {page} of {totalPages || 1} ({total} jobs)
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-3 py-1.5 text-xs rounded border border-[#1a2744] bg-[#111b2e] text-[#d4dce8] disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[#1a2744]"
          >
            Previous
          </button>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1.5 text-xs rounded border border-[#1a2744] bg-[#111b2e] text-[#d4dce8] disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[#1a2744]"
          >
            Next
          </button>
        </div>
      </div>

      {/* Detail Slide Panel */}
      {selectedJob && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/50" onClick={() => setSelectedJob(null)} />
          <div className="relative w-full max-w-xl bg-[#0b1120] border-l border-[#1a2744] overflow-auto">
            <div className="sticky top-0 flex items-center justify-between px-6 py-4 border-b border-[#1a2744] bg-[#0b1120]">
              <h3 className="text-sm font-semibold text-[#d4dce8]">Job Details</h3>
              <button
                onClick={() => setSelectedJob(null)}
                className="text-[#5a6f8a] hover:text-[#d4dce8] text-lg"
              >
                &times;
              </button>
            </div>

            {panelLoading ? (
              <div className="p-6 text-[#5a6f8a]">Loading...</div>
            ) : (
              <div className="p-6 space-y-5">
                {/* Header */}
                <div>
                  <h4 className="text-lg font-semibold text-[#d4dce8]">{selectedJob.title || 'Untitled'}</h4>
                  <p className="text-sm text-[#e8a317] mt-1">{selectedJob.company || 'Unknown'}</p>
                  <div className="flex items-center gap-3 mt-2">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium ${scoreColor(selectedJob.fit_score)}`}>
                      Score: {selectedJob.fit_score ?? 'N/A'}
                    </span>
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${statusColor(selectedJob.status)}`}>
                      {selectedJob.status.replace(/_/g, ' ')}
                    </span>
                  </div>
                </div>

                {/* Meta */}
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#5a6f8a]">
                  {selectedJob.location && <span>📍 {selectedJob.location}</span>}
                  {selectedJob.employment_type && <span>{selectedJob.employment_type}</span>}
                  {(selectedJob.salary_min || selectedJob.salary_max) && (
                    <span>💰 {selectedJob.salary_min ? Math.round(selectedJob.salary_min).toLocaleString() : '?'}–{selectedJob.salary_max ? Math.round(selectedJob.salary_max).toLocaleString() : '?'} {selectedJob.salary_currency || ''}</span>
                  )}
                  {selectedJob.posted_at && <span>posted {selectedJob.posted_at}</span>}
                  {selectedJob.source && <span>via {selectedJob.source}</span>}
                  {selectedJob.low_confidence ? <span className="text-orange-400">low confidence (no full description)</span> : null}
                </div>

                {/* Score facts (v2 scorer breakdown; JSON or NULL) */}
                {scoreFacts && scoreFacts.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {scoreFacts.map(([k, v]) => (
                      <span key={k} className="px-2 py-0.5 rounded border border-[#1a2744] bg-[#111b2e] text-xs text-[#5a6f8a]">
                        <span className="text-[#d4dce8]">{k}</span>: {v}
                      </span>
                    ))}
                  </div>
                )}

                {/* URL */}
                {selectedJob.url && (
                  <div>
                    <p className="text-xs text-[#5a6f8a] mb-1">URL</p>
                    <a
                      href={selectedJob.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-400 hover:underline break-all"
                    >
                      {selectedJob.url}
                    </a>
                  </div>
                )}

                {/* Description */}
                {(selectedJob.description || selectedJob.snippet) && (
                  <details className="group">
                    <summary className="text-xs text-[#5a6f8a] mb-1 cursor-pointer hover:text-[#d4dce8]">Job description</summary>
                    <p className="text-sm text-[#d4dce8] whitespace-pre-wrap max-h-72 overflow-auto rounded bg-[#0b1120] p-3 border border-[#1a2744]">{selectedJob.description || selectedJob.snippet}</p>
                  </details>
                )}

                {/* Reasoning */}
                {selectedJob.fit_reasoning && (
                  <div>
                    <p className="text-xs text-[#5a6f8a] mb-1">Fit Reasoning</p>
                    <p className="text-sm text-[#d4dce8] leading-relaxed">{selectedJob.fit_reasoning}</p>
                  </div>
                )}

                {/* Strengths */}
                {selectedJob.strengths && selectedJob.strengths.length > 0 && (
                  <div>
                    <p className="text-xs text-[#5a6f8a] mb-2">Strengths</p>
                    <ul className="space-y-1">
                      {selectedJob.strengths.map((s, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-green-400">
                          <span className="mt-1">&#x2022;</span>
                          <span>{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Gaps */}
                {selectedJob.gaps && selectedJob.gaps.length > 0 && (
                  <div>
                    <p className="text-xs text-[#5a6f8a] mb-2">Gaps</p>
                    <ul className="space-y-1">
                      {selectedJob.gaps.map((g, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-red-400">
                          <span className="mt-1">&#x2022;</span>
                          <span>{g}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Prefilter reason */}
                {selectedJob.prefilter_reason && (
                  <div>
                    <p className="text-xs text-[#5a6f8a] mb-1">Dropped by rule</p>
                    <p className="text-sm text-[#d4dce8]">{selectedJob.prefilter_reason}</p>
                  </div>
                )}

                {/* Skip / expiry reason */}
                {selectedJob.skip_reason && (
                  <div>
                    <p className="text-xs text-[#5a6f8a] mb-1">{selectedJob.status === 'expired' ? 'Retired from the queue' : 'Skip Reason'}</p>
                    <p className="text-sm text-[#d4dce8]">{selectedJob.skip_reason}</p>
                  </div>
                )}

                {/* PDFs */}
                {!selectedJob.output_folder && selectedJob.fit_score !== null && (
                  <div>
                    <p className="text-xs text-[#5a6f8a] mb-2">Documents</p>
                    <button onClick={handleDocs} disabled={actioning}
                      className="px-3 py-1.5 text-xs rounded border border-[rgba(232,163,23,0.25)] bg-[rgba(232,163,23,0.12)] text-[#e8a317] hover:bg-[rgba(232,163,23,0.25)] disabled:opacity-50">
                      Generate tailored resume + cover letter
                    </button>
                  </div>
                )}
                {selectedJob.output_folder && (
                  <div>
                    <p className="text-xs text-[#5a6f8a] mb-2">Generated Documents</p>
                    <div className="flex gap-2">
                      <a
                        href={`/api/autojob/pdf/${selectedJob.id}/resume.pdf`}
                        target="_blank"
                        className="px-3 py-1.5 text-xs rounded border border-[#1a2744] bg-[#111b2e] text-[#d4dce8] hover:bg-[#1a2744]"
                      >
                        Resume PDF
                      </a>
                      <a
                        href={`/api/autojob/pdf/${selectedJob.id}/cover_letter.pdf`}
                        target="_blank"
                        className="px-3 py-1.5 text-xs rounded border border-[#1a2744] bg-[#111b2e] text-[#d4dce8] hover:bg-[#1a2744]"
                      >
                        Cover Letter PDF
                      </a>
                    </div>
                  </div>
                )}

                {/* Actions */}
                {!actionedIds.has(selectedJob.id) && !selectedJob.user_action ? (
                  <div className="pt-3 border-t border-[#1a2744] space-y-2">
                    <button
                      onClick={handleApply}
                      disabled={actioning}
                      className="w-full px-4 py-2 text-sm rounded bg-green-900/30 text-green-400 border border-green-900/50 hover:bg-green-900/50 disabled:opacity-50 transition-colors"
                    >
                      {actioning ? 'Applying...' : 'Apply — promote to tracker'}
                    </button>
                    <button
                      onClick={() => (dismissArmed ? handleDismiss(null) : setDismissArmed(true))}
                      disabled={actioning}
                      className="w-full px-4 py-2 text-sm rounded bg-[#111b2e] text-[#5a6f8a] border border-[#1a2744] hover:bg-[#1a2744] hover:text-[#d4dce8] disabled:opacity-50 transition-colors"
                    >
                      {actioning ? 'Dismissing...' : dismissArmed ? 'Dismiss — no reason' : 'Dismiss — not a fit'}
                    </button>
                    {dismissArmed && !actioning && (
                      <div className="flex flex-wrap gap-1.5">
                        {DISMISS_REASONS.map((r, i) => (
                          <button
                            key={r.slug}
                            onClick={() => handleDismiss(r.slug)}
                            title={`Key ${i + 1}`}
                            className="px-2 py-1 rounded border border-[#1a2744] bg-[#111b2e] text-xs text-[#d4dce8] hover:bg-[#1a2744] hover:text-[#e8a317] transition-colors"
                          >
                            <span className="text-[#5a6f8a] font-mono mr-1">{i + 1}</span>{r.label}
                          </button>
                        ))}
                      </div>
                    )}
                    <p className="text-[10px] text-[#5a6f8a]">
                      keys: j/k move · o/Enter open · a apply · d dismiss (again or Esc = no reason) · 1–7 reason · Esc close
                    </p>
                  </div>
                ) : (
                  <div className="pt-3 border-t border-[#1a2744]">
                    <p className="text-xs text-[#5a6f8a]">You marked this as <span className="text-[#d4dce8]">{selectedJob.user_action || 'actioned'}</span>{selectedJob.user_action === 'dismissed' && selectedJob.dismiss_reason ? ` (${selectedJob.dismiss_reason})` : ''}{selectedJob.user_action_at ? ` on ${new Date(selectedJob.user_action_at).toLocaleDateString()}` : ''}</p>
                  </div>
                )}

                {actionMsg && (
                  <p className="text-xs text-[#e8a317]">{actionMsg}</p>
                )}

                {/* Dates */}
                <div className="text-xs text-[#5a6f8a] space-y-1">
                  <p>Fetched: {selectedJob.fetched_at ? new Date(selectedJob.fetched_at).toLocaleString() : '-'}</p>
                  <p>Scored: {selectedJob.scored_at ? new Date(selectedJob.scored_at).toLocaleString() : '-'}{selectedJob.scorer_model ? ` · ${selectedJob.scorer_model}` : ''}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

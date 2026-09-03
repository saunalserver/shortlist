import Link from 'next/link';
import { fetchAutojobStats, fetchRecentRuns, fetchPipelineState } from '@/actions/autojob';
import { RunControls } from './run-controls';

export const dynamic = 'force-dynamic';

function StatCard({ title, value, accent, href }: { title: string; value: string | number; accent?: boolean; href?: string }) {
  const body = (
    <div className="rounded-lg border border-[#1a2744] bg-[#111b2e] p-5 hover:border-[#2a3a5c] transition-colors">
      <p className="text-xs font-medium uppercase tracking-wider text-[#5a6f8a]">{title}</p>
      <p className={`text-3xl font-bold mt-2 ${accent ? 'text-[#e8a317]' : 'text-[#d4dce8]'}`}>{value}</p>
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

function ScoreDistribution({ distribution }: { distribution: { range: string; count: number }[] }) {
  const maxCount = Math.max(...distribution.map(d => d.count), 1);
  return (
    <div className="rounded-lg border border-[#1a2744] bg-[#111b2e] p-5">
      <h3 className="text-sm font-medium text-[#5a6f8a] mb-4">Score distribution (all scored jobs)</h3>
      <div className="flex items-end gap-3 h-40">
        {distribution.map(({ range, count }) => (
          <div key={range} className="flex-1 flex flex-col items-center gap-1">
            <span className="text-xs text-[#5a6f8a]">{count}</span>
            <div className="w-full relative" style={{ height: '120px' }}>
              <div className="absolute bottom-0 w-full rounded-t"
                style={{ height: `${(count / maxCount) * 100}%`, background: 'rgba(232,163,23,0.6)', minHeight: count > 0 ? '4px' : '0px' }} />
            </div>
            <span className="text-xs text-[#5a6f8a]">{range}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Funnel({ byStatus, total }: { byStatus: Record<string, number>; total: number }) {
  const steps: [string, string, string][] = [
    ['new', 'Fetched, not yet scored', 'bg-blue-500'],
    ['prefiltered', 'Dropped by rules (no LLM call)', 'bg-gray-600'],
    ['skipped', 'Scored below the bar', 'bg-gray-500'],
    ['queued', 'Worth a look', 'bg-yellow-500'],
    ['docs_generated', 'Documents ready', 'bg-green-500'],
    ['expired', 'Shortlisted, then retired (too old or posting gone)', 'bg-gray-700'],
    ['error', 'Scoring error (retried next run)', 'bg-red-500'],
  ];
  return (
    <div className="rounded-lg border border-[#1a2744] bg-[#111b2e] p-5">
      <h3 className="text-sm font-medium text-[#5a6f8a] mb-4">Funnel · {total} jobs ever seen</h3>
      <div className="space-y-2">
        {steps.map(([key, label, color]) => (
          <div key={key} className="flex items-center gap-3 text-xs">
            <div className={`w-2 h-2 rounded-sm ${color}`} />
            <span className="text-[#d4dce8] capitalize w-32">{key.replace(/_/g, ' ')}</span>
            <span className="text-[#5a6f8a] flex-1">{label}</span>
            <span className="text-[#d4dce8] font-mono">{byStatus[key] || 0}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function fmt(ts: string | null) {
  return ts ? new Date(ts).toLocaleString('en-CA', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '–';
}

function minutes(a: string, b: string | null) {
  if (!b) return '…';
  return `${Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60000)} min`;
}

export default async function PipelineDashboardPage() {
  const [stats, runs, state] = await Promise.all([fetchAutojobStats(), fetchRecentRuns(10), fetchPipelineState()]);

  return (
    <>
      <header className="h-16 border-b border-[#1a2744] flex items-center justify-between px-6">
        <h2 className="text-lg font-semibold text-[#d4dce8]">Pipeline</h2>
        <RunControls initialState={state} />
      </header>

      <div className="flex-1 overflow-auto p-6 space-y-6 bg-[#060a12]">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="To review" value={stats.pendingReview} accent href="/pipeline/jobs" />
          <StatCard title="Fetched last 7 days" value={stats.last7Days} />
          <StatCard title="Shortlisted last 7 days" value={stats.shortlisted7Days} />
          <StatCard title="Retired (old / gone)" value={stats.expired} href="/pipeline/jobs" />
        </div>

        <div className="rounded-lg border border-[#1a2744] bg-[#111b2e] p-5">
          <h3 className="text-sm font-medium text-[#5a6f8a] mb-3">Recent runs</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-[#5a6f8a] uppercase tracking-wider">
                <tr className="text-left">
                  <th className="py-2 pr-4">Started</th><th className="py-2 pr-4">Took</th><th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4 text-right">Fetched</th><th className="py-2 pr-4 text-right">New</th>
                  <th className="py-2 pr-4 text-right">Filtered</th><th className="py-2 pr-4 text-right">Scored</th>
                  <th className="py-2 pr-4 text-right">Queued</th><th className="py-2 pr-4 text-right">Docs</th>
                  <th className="py-2 pr-4 text-right">Errors</th><th className="py-2 pr-4 text-right">Retired</th><th className="py-2 text-right">LLM calls</th>
                </tr>
              </thead>
              <tbody className="text-[#d4dce8]">
                {runs.length === 0 && <tr><td colSpan={12} className="py-6 text-center text-[#5a6f8a]">No runs yet</td></tr>}
                {runs.map(r => (
                  <tr key={r.id} className="border-t border-[#1a2744]">
                    <td className="py-2 pr-4">{fmt(r.started_at)}{r.dry_run ? <span className="ml-1 text-[#5a6f8a]">(dry)</span> : null}</td>
                    <td className="py-2 pr-4 text-[#5a6f8a]">{minutes(r.started_at, r.finished_at)}</td>
                    <td className={`py-2 pr-4 ${r.status === 'done' ? 'text-green-400' : r.status === 'running' ? 'text-[#e8a317]' : 'text-red-400'}`}>{r.status}</td>
                    <td className="py-2 pr-4 text-right font-mono">{r.fetched}</td>
                    <td className="py-2 pr-4 text-right font-mono">{r.new_jobs}</td>
                    <td className="py-2 pr-4 text-right font-mono text-[#5a6f8a]">{r.prefiltered}</td>
                    <td className="py-2 pr-4 text-right font-mono">{r.scored}</td>
                    <td className="py-2 pr-4 text-right font-mono text-[#e8a317]">{r.queued}</td>
                    <td className="py-2 pr-4 text-right font-mono text-green-400">{r.docs}</td>
                    <td className="py-2 pr-4 text-right font-mono text-red-400">{r.errors || ''}</td>
                    <td className="py-2 pr-4 text-right font-mono text-[#5a6f8a]">{r.expired || ''}</td>
                    <td className="py-2 text-right font-mono text-[#5a6f8a]">{r.llm_calls}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ScoreDistribution distribution={stats.scoreDistribution} />
          <Funnel byStatus={stats.byStatus} total={stats.totalJobs} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-lg border border-[#1a2744] bg-[#111b2e] p-5">
            <h3 className="text-sm font-medium text-[#5a6f8a] mb-4">Jobs by source</h3>
            <div className="space-y-1">
              {stats.bySource.map(({ source, count }) => (
                <div key={source} className="flex items-center justify-between text-sm py-1">
                  <span className="text-[#d4dce8]">{source}</span>
                  <span className="font-mono text-[#5a6f8a]">{count}</span>
                </div>
              ))}
            </div>
            <Link href="/pipeline/sources" className="inline-block mt-3 text-xs text-[#e8a317] hover:underline">Source health →</Link>
          </div>
          <div className="rounded-lg border border-[#1a2744] bg-[#111b2e] p-5">
            <h3 className="text-sm font-medium text-[#5a6f8a] mb-4">Companies with the most shortlisted roles</h3>
            <div className="space-y-1">
              {stats.topCompanies.length === 0 && <p className="text-sm text-[#5a6f8a]">Nothing shortlisted yet</p>}
              {stats.topCompanies.map(({ company, count }) => (
                <div key={company} className="flex items-center justify-between text-sm py-1">
                  <span className="text-[#d4dce8] truncate">{company}</span>
                  <span className="font-mono text-[#e8a317] ml-4">{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

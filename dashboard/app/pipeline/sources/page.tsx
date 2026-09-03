import { fetchSourceHealth, fetchSearchConfig } from '@/actions/autojob';

export const dynamic = 'force-dynamic';

function ago(ts: string) {
  const h = Math.round((Date.now() - new Date(ts).getTime()) / 3600_000);
  return h < 1 ? 'just now' : h < 48 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
}

export default async function PipelineSourcesPage() {
  const [health, config] = await Promise.all([fetchSourceHealth(), fetchSearchConfig()]);

  return (
    <div className="flex h-full flex-col bg-[#060a12]">
      <header className="h-16 border-b border-[#1a2744] flex items-center px-6">
        <h2 className="text-lg font-semibold text-[#d4dce8]">Sources</h2>
      </header>

      <div className="flex-1 overflow-auto p-6 space-y-6">
        <div className="rounded-lg border border-[#1a2744] bg-[#111b2e] p-5">
          <h3 className="text-sm font-medium text-[#d4dce8] mb-1">Last result per source</h3>
          <p className="text-xs text-[#5a6f8a] mb-4">“New” is what the source contributed after de-duplication. A source that is red or always zero is worth disabling in <code>config/search.yaml</code>.</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-[#5a6f8a] uppercase tracking-wider text-left">
                <tr>
                  <th className="py-2 pr-4">Source</th><th className="py-2 pr-4">Last run</th>
                  <th className="py-2 pr-4 text-right">Fetched</th><th className="py-2 pr-4 text-right">New</th>
                  <th className="py-2 pr-4 text-right">Took</th><th className="py-2 pr-4 text-right">Total ever</th>
                  <th className="py-2 pr-4 text-right">Shortlisted</th><th className="py-2">Error</th>
                </tr>
              </thead>
              <tbody className="text-[#d4dce8]">
                {health.length === 0 && <tr><td colSpan={8} className="py-6 text-center text-[#5a6f8a]">No runs recorded yet</td></tr>}
                {health.map(s => (
                  <tr key={s.source} className="border-t border-[#1a2744]">
                    <td className="py-2 pr-4 font-medium">{s.source}</td>
                    <td className="py-2 pr-4 text-[#5a6f8a]">{ago(s.last_run)}</td>
                    <td className="py-2 pr-4 text-right font-mono">{s.fetched}</td>
                    <td className="py-2 pr-4 text-right font-mono text-[#e8a317]">{s.new_jobs}</td>
                    <td className="py-2 pr-4 text-right font-mono text-[#5a6f8a]">{s.duration_s != null ? `${Math.round(s.duration_s)} s` : ''}</td>
                    <td className="py-2 pr-4 text-right font-mono">{s.total_jobs}</td>
                    <td className="py-2 pr-4 text-right font-mono text-green-400">{s.queued_jobs}</td>
                    <td className="py-2 text-red-400 truncate max-w-xs">{s.error || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-lg border border-[#1a2744] bg-[#111b2e] p-5">
          <h3 className="text-sm font-medium text-[#d4dce8] mb-1">config/search.yaml (read-only)</h3>
          <p className="text-xs text-[#5a6f8a] mb-3">Queries, prefilter rules, model list, per-source settings and company boards. Edit config in the pipeline directory; changes apply on the next run.</p>
          <pre className="text-xs text-[#a9b6c9] bg-[#0b1120] rounded p-4 overflow-auto whitespace-pre font-mono border border-[#1a2744] max-h-[70vh]">{config}</pre>
        </div>
      </div>
    </div>
  );
}

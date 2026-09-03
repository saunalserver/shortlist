'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchAutojobLogs } from '@/actions/autojob';

function lineClass(line: string): string {
  const u = line.toUpperCase();
  if (u.includes('[ERROR]') || u.includes('TRACEBACK') || u.includes('[CRITICAL]')) return 'text-red-400';
  if (u.includes('[WARNING]')) return 'text-orange-400';
  if (u.includes('===')) return 'text-[#e8a317]';
  return 'text-[#d4dce8]';
}

export default function PipelineLogsPage() {
  const [lines, setLines] = useState<string[]>([]);
  const [lineCount, setLineCount] = useState(200);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLines(await fetchAutojobLogs(lineCount));
    setLoading(false);
  }, [lineCount]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!autoRefresh) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [autoRefresh, load]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [lines]);

  return (
    <div className="flex h-full flex-col bg-[#060a12]">
      <header className="h-16 border-b border-[#1a2744] flex items-center justify-between px-6">
        <h2 className="text-lg font-semibold text-[#d4dce8]">Pipeline logs</h2>
        <div className="flex items-center gap-3">
          <select value={lineCount} onChange={(e) => setLineCount(parseInt(e.target.value, 10))}
            className="h-8 rounded border border-[#1a2744] bg-[#111b2e] px-2 text-xs text-[#d4dce8] focus:outline-none focus:ring-1 focus:ring-[#e8a317]">
            <option value={100}>100 lines</option><option value={200}>200 lines</option><option value={500}>500 lines</option><option value={1000}>1000 lines</option>
          </select>
          <label className="flex items-center gap-2 text-xs text-[#5a6f8a]">
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} className="accent-[#e8a317]" />
            Auto-refresh
          </label>
          <button onClick={() => { setLoading(true); load(); }}
            className="px-3 py-1.5 text-xs rounded border border-[#1a2744] bg-[#111b2e] text-[#d4dce8] hover:bg-[#1a2744]">Refresh</button>
        </div>
      </header>
      <div className="flex-1 overflow-auto bg-[#0b1120] font-mono text-xs">
        {loading ? <div className="flex items-center justify-center h-64 text-[#5a6f8a]">Loading logs…</div> : (
          <div className="p-4">
            {lines.map((line, i) => <div key={i} className={`${lineClass(line)} whitespace-pre-wrap break-all leading-5`}>{line}</div>)}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
      <div className="px-6 py-2 border-t border-[#1a2744] bg-[#0b1120]">
        <span className="text-xs text-[#5a6f8a]">{lines.length} lines{autoRefresh ? ' · auto-refresh 4 s' : ''} · run controls are on the Pipeline page</span>
      </div>
    </div>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { fetchPipelineState, triggerAutojobRun, abortPipeline } from '@/actions/autojob';
import type { PipelineState } from '@/lib/autojob-db';

const PHASES: Record<string, string> = {
  init: 'Starting', expiring: 'Retiring old postings', inserting: 'Saving jobs', prefiltering: 'Applying rules', scraping: 'Fetching descriptions',
  scoring: 'Scoring', generating: 'Generating documents', notifying: 'Sending digest', done: 'Done', aborted: 'Aborted', error: 'Error',
};

export function RunControls({ initialState }: { initialState: PipelineState }) {
  const [state, setState] = useState<PipelineState>(initialState);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = setInterval(async () => setState(await fetchPipelineState()), 4000);
    return () => clearInterval(t);
  }, []);

  const act = async (fn: () => Promise<{ success: boolean; message: string }>) => {
    setBusy(true);
    const r = await fn();
    setMsg(r.message);
    setState(await fetchPipelineState());
    setBusy(false);
    setTimeout(() => setMsg(''), 6000);
  };

  const phase = state.current_phase || '';
  const label = state.running
    ? (phase.startsWith('fetching:') ? `Fetching ${phase.split(':')[1]}` : PHASES[phase] || 'Running')
    : (PHASES[phase] && phase !== 'done' ? PHASES[phase] : 'Idle');
  const progress = state.running && state.jobs_total ? ` ${state.jobs_processed ?? 0}/${state.jobs_total}` : '';

  return (
    <div className="flex items-center gap-3">
      {msg && <span className="text-xs text-[#e8a317]">{msg}</span>}
      <span className="flex items-center gap-2 text-xs text-[#d4dce8]">
        <span className={`w-2 h-2 rounded-full ${state.running ? 'bg-[#e8a317] animate-pulse' : 'bg-[#22c55e]'}`} />
        {label}{progress}
      </span>
      {state.running ? (
        <button onClick={() => act(abortPipeline)} disabled={busy}
          className="px-3 py-1.5 text-xs rounded border border-[rgba(239,68,68,0.25)] text-[#ef4444] hover:bg-[rgba(239,68,68,0.12)] disabled:opacity-50">
          Abort
        </button>
      ) : (
        <>
          <button onClick={() => act(() => triggerAutojobRun(true))} disabled={busy}
            className="px-3 py-1.5 text-xs rounded border border-[#1a2744] bg-[#111b2e] text-[#d4dce8] hover:bg-[#1a2744] disabled:opacity-50">
            Dry run
          </button>
          <button onClick={() => act(() => triggerAutojobRun(false))} disabled={busy}
            className="px-3 py-1.5 text-xs rounded border border-[rgba(232,163,23,0.25)] bg-[rgba(232,163,23,0.12)] text-[#e8a317] hover:bg-[rgba(232,163,23,0.25)] disabled:opacity-50">
            Run now
          </button>
        </>
      )}
    </div>
  );
}

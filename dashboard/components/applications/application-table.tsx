'use client';

import { useState } from 'react';
import { Application, ApplicationStatus } from '@/lib/types';
import { formatDate } from '@/lib/utils';
import { StatusBadge } from './status-badge';
import { Button } from '@/components/ui/button';
import { ExternalLink, Pencil, Trash2 } from 'lucide-react';
import { deleteApplicationById, updateExistingApplication } from '@/actions/applications';
import { useRouter } from 'next/navigation';
import { useUIStore } from '@/store/ui-store';
import { QUICK_STATUSES, STATUS_LABELS } from '@/lib/constants';

interface ApplicationTableProps {
  applications: Application[];
  compact?: boolean;
  /** Called after a quick-status change so the parent can refresh its copy in place. */
  onUpdated?: (app: Application) => void;
}

export function ApplicationTable({ applications, compact, onUpdated }: ApplicationTableProps) {
  const router = useRouter();
  const openPanel = useUIStore((state) => state.openPanel);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this application?')) return;
    await deleteApplicationById(id);
    router.refresh();
  };

  const handleQuickStatus = async (id: string, status: ApplicationStatus) => {
    setUpdatingId(id);
    try {
      const updated = await updateExistingApplication(id, { status });
      if (updated) onUpdated?.(updated);
    } finally {
      setUpdatingId(null);
    }
  };

  if (applications.length === 0) {
    return (
      <div className="text-center text-muted-foreground py-8">
        No applications found. Click &quot;Add Application&quot; to get started.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b text-left text-sm text-muted-foreground">
            <th className="pb-3 font-medium">Company</th>
            <th className="pb-3 font-medium">Role</th>
            {!compact && <th className="pb-3 font-medium">Status</th>}
            {!compact && <th className="pb-3 font-medium">Source</th>}
            <th className="pb-3 font-medium">Applied</th>
            {!compact && <th className="pb-3 font-medium">Location</th>}
            <th className="pb-3 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {applications.map((app) => (
            <tr key={app.id} className="border-b last:border-0">
              <td className="py-3">
                <div>
                  <p className="font-medium">{app.company_name}</p>
                  {compact && (
                    <p className="text-xs text-muted-foreground">{app.role_title}</p>
                  )}
                </div>
              </td>
              {!compact && <td className="py-3 text-sm">{app.role_title}</td>}
              {!compact && (
                <td className="py-3">
                  <StatusBadge status={app.status} />
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {QUICK_STATUSES.map(s => (
                      <button
                        key={s}
                        onClick={() => handleQuickStatus(app.id, s)}
                        disabled={updatingId === app.id || app.status === s}
                        title={`Move to ${STATUS_LABELS[s]}`}
                        className={`rounded border px-1.5 py-0.5 text-[11px] transition-colors disabled:cursor-default ${
                          app.status === s
                            ? 'border-primary/40 bg-primary/10 text-primary'
                            : 'border-border text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                        }`}
                      >
                        {STATUS_LABELS[s]}
                      </button>
                    ))}
                  </div>
                </td>
              )}
              {!compact && (
                <td className="py-3 text-sm text-muted-foreground">
                  {app.source || '-'}
                </td>
              )}
              <td className="py-3 text-sm text-muted-foreground">
                {formatDate(app.date_applied)}
              </td>
              {!compact && (
                <td className="py-3 text-sm text-muted-foreground">
                  {app.location || '-'}
                </td>
              )}
              <td className="py-3 text-right">
                <div className="flex items-center justify-end gap-1">
                  {app.posting_url && (
                    <a
                      href={app.posting_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground h-9 w-9"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => openPanel(app.id)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDelete(app.id)}
                    className="text-destructive hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

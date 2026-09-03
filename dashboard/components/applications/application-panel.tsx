'use client';

import { useEffect, useState } from 'react';
import { X, ExternalLink, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Application } from '@/lib/types';
import { fetchApplication, deleteApplicationById } from '@/actions/applications';
import { ApplicationForm } from './application-form';
import { useUIStore } from '@/store/ui-store';
import { useRouter } from 'next/navigation';

export function ApplicationPanel() {
  const router = useRouter();
  const { selectedApplicationId, isPanelOpen, closePanel } = useUIStore();
  const [application, setApplication] = useState<Application | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (selectedApplicationId && isPanelOpen) {
      setIsLoading(true);
      fetchApplication(selectedApplicationId).then((app) => {
        setApplication(app);
        setIsLoading(false);
      });
    }
  }, [selectedApplicationId, isPanelOpen]);

  const handleDelete = async () => {
    if (!application) return;
    if (!confirm('Are you sure you want to delete this application?')) return;

    await deleteApplicationById(application.id);
    closePanel();
    router.refresh();
  };

  const handleSuccess = (updatedApp: Application) => {
    setApplication(updatedApp);
    router.refresh();
  };

  if (!isPanelOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={closePanel}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-full max-w-lg bg-background border-l shadow-xl z-50 overflow-y-auto">
        <div className="sticky top-0 bg-background border-b px-6 py-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">
            {isLoading ? 'Loading...' : application ? 'Edit Application' : 'New Application'}
          </h3>
          <div className="flex items-center gap-2">
            {application?.posting_url && (
              <a
                href={application.posting_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground h-9 w-9"
              >
                <ExternalLink className="h-4 w-4" />
              </a>
            )}
            {application && (
              <Button
                variant="ghost"
                size="icon"
                onClick={handleDelete}
                className="text-destructive hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
            <Button variant="ghost" size="icon" onClick={closePanel}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="p-6">
          {isLoading ? (
            <div className="text-center text-muted-foreground py-8">Loading...</div>
          ) : (
            <>
              <ApplicationForm
                application={application}
                onSuccess={handleSuccess}
                onCancel={closePanel}
              />
            </>
          )}
        </div>
      </div>
    </>
  );
}

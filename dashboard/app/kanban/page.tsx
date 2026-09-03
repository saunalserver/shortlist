'use client';

import { useEffect, useState, useCallback } from 'react';
import { Header } from '@/components/layout/header';
import { KanbanBoard } from '@/components/applications/kanban-board';
import { fetchApplications } from '@/actions/applications';
import { Application } from '@/lib/types';
import { useRouter } from 'next/navigation';

export default function KanbanPage() {
  const router = useRouter();
  const [applications, setApplications] = useState<Application[]>([]);

  useEffect(() => {
    fetchApplications().then(setApplications);
  }, []);

  const handleMutation = useCallback(() => {
    router.refresh();
    fetchApplications().then(setApplications);
  }, [router]);

  return (
    <>
      <Header title="Kanban Board" />
      <div className="flex-1 overflow-auto p-6">
        <KanbanBoard
          applications={applications}
          onMutation={handleMutation}
        />
      </div>
    </>
  );
}

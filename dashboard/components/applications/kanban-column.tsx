'use client';

import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { Application, ApplicationStatus } from '@/lib/types';
import { STATUS_LABELS } from '@/lib/constants';
import { KanbanCard } from './kanban-card';
import { cn } from '@/lib/utils';

interface KanbanColumnProps {
  status: ApplicationStatus;
  applications: Application[];
}

export function KanbanColumn({ status, applications }: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: status,
  });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'flex-1 min-w-[280px] max-w-[320px] bg-muted/30 rounded-lg p-3',
        isOver && 'bg-muted/50 ring-2 ring-primary'
      )}
    >
      <div className="flex items-center justify-between mb-3 px-1">
        <h3 className="font-medium text-sm">{STATUS_LABELS[status]}</h3>
        <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
          {applications.length}
        </span>
      </div>

      <SortableContext
        items={applications.map((a) => a.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="space-y-2">
          {applications.map((application) => (
            <KanbanCard key={application.id} application={application} />
          ))}
        </div>
      </SortableContext>
    </div>
  );
}

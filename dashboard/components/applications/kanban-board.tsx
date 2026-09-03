'use client';

import { useState } from 'react';
import {
  DndContext,
  DragOverlay,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
  DragStartEvent,
} from '@dnd-kit/core';
import { Application, ApplicationStatus } from '@/lib/types';
import { KANBAN_STATUSES, TERMINAL_STATUSES } from '@/lib/constants';
import { KanbanColumn } from './kanban-column';
import { updateExistingApplication } from '@/actions/applications';
import { Card, CardContent } from '@/components/ui/card';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface KanbanBoardProps {
  applications: Application[];
  onMutation: () => void;
}

export function KanbanBoard({ applications, onMutation }: KanbanBoardProps) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [showTerminal, setShowTerminal] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor)
  );

  const activeApplication = activeId
    ? applications.find((a) => a.id === activeId)
    : null;

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);

    if (!over) return;

    const applicationId = active.id as string;
    const newStatus = over.id as ApplicationStatus;

    const application = applications.find((a) => a.id === applicationId);
    if (!application || application.status === newStatus) return;

    await updateExistingApplication(applicationId, { status: newStatus });
    onMutation();
  };

  const getApplicationsByStatus = (status: ApplicationStatus) =>
    applications.filter((a) => a.status === status);

  const terminalApplications = TERMINAL_STATUSES.flatMap((status) =>
    applications.filter((a) => a.status === status)
  );

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 overflow-x-auto pb-4">
        {KANBAN_STATUSES.map((status) => (
          <KanbanColumn
            key={status}
            status={status}
            applications={getApplicationsByStatus(status)}
          />
        ))}
      </div>

      {/* Terminal States (Collapsible) */}
      {terminalApplications.length > 0 && (
        <div className="mt-6">
          <button
            onClick={() => setShowTerminal(!showTerminal)}
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-3"
          >
            {showTerminal ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
            Completed ({terminalApplications.length})
          </button>

          {showTerminal && (
            <div className="flex gap-4 overflow-x-auto pb-4">
              {TERMINAL_STATUSES.map((status) => {
                const apps = getApplicationsByStatus(status);
                if (apps.length === 0) return null;
                return (
                  <KanbanColumn key={status} status={status} applications={apps} />
                );
              })}
            </div>
          )}
        </div>
      )}

      <DragOverlay>
        {activeApplication ? (
          <div className="opacity-90">
            <Card>
              <CardContent className="p-3">
                <p className="font-medium text-sm">{activeApplication.company_name}</p>
                <p className="text-xs text-muted-foreground">{activeApplication.role_title}</p>
              </CardContent>
            </Card>
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}

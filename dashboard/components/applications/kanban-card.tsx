'use client';

import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Application } from '@/lib/types';
import { formatDaysAgo } from '@/lib/utils';
import { useUIStore } from '@/store/ui-store';
import { GripVertical } from 'lucide-react';

interface KanbanCardProps {
  application: Application;
}

export function KanbanCard({ application }: KanbanCardProps) {
  const openPanel = useUIStore((state) => state.openPanel);

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: application.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <Card
      ref={setNodeRef}
      style={style}
      className={`cursor-pointer hover:shadow-md transition-shadow ${
        isDragging ? 'opacity-50 shadow-lg' : ''
      }`}
      onClick={() => openPanel(application.id)}
    >
      <CardContent className="p-3">
        <div className="flex items-start gap-2">
          <button
            {...attributes}
            {...listeners}
            className="mt-1 cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground"
          >
            <GripVertical className="h-4 w-4" />
          </button>
          <div className="flex-1 min-w-0">
            <p className="font-medium text-sm truncate">{application.company_name}</p>
            <p className="text-xs text-muted-foreground truncate">{application.role_title}</p>

            <div className="flex items-center gap-2 mt-2">
              {application.date_applied && (
                <span className="text-xs text-muted-foreground">
                  {formatDaysAgo(application.date_applied)}
                </span>
              )}
            </div>

            {application.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {application.tags.slice(0, 2).map((tag) => (
                  <Badge key={tag} variant="outline" className="text-xs">
                    {tag}
                  </Badge>
                ))}
                {application.tags.length > 2 && (
                  <Badge variant="outline" className="text-xs">
                    +{application.tags.length - 2}
                  </Badge>
                )}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

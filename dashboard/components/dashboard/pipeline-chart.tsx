'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DashboardStats } from '@/lib/types';
import { STATUS_LABELS, KANBAN_STATUSES } from '@/lib/constants';

interface PipelineChartProps {
  stats: DashboardStats;
}

export function PipelineChart({ stats }: PipelineChartProps) {
  const data = KANBAN_STATUSES.map((status) => ({
    name: STATUS_LABELS[status],
    count: stats.byStatus[status] || 0,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Pipeline by Stage</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[200px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis dataKey="name" type="category" width={80} fontSize={12} />
              <Tooltip />
              <Bar dataKey="count" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

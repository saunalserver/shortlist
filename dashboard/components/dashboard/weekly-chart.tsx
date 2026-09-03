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
import { format } from 'date-fns';

interface WeeklyChartProps {
  stats: DashboardStats;
}

export function WeeklyChart({ stats }: WeeklyChartProps) {
  const data = stats.weeklyApplications.map((item) => ({
    name: format(new Date(item.week), 'MMM d'),
    count: item.count,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Applications per Week</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[200px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" fontSize={12} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

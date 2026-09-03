import { Header } from '@/components/layout/header';
import { StatCard } from '@/components/dashboard/stat-card';
import { PipelineChart } from '@/components/dashboard/pipeline-chart';
import { WeeklyChart } from '@/components/dashboard/weekly-chart';
import { fetchStats, fetchApplications } from '@/actions/applications';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ApplicationTable } from '@/components/applications/application-table';

export const dynamic = 'force-dynamic';

export default async function DashboardPage() {
  const stats = await fetchStats();
  const recentApplications = await fetchApplications({});

  return (
    <>
      <Header title="Dashboard" />

      <div className="flex-1 overflow-auto p-6 space-y-6">
        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="Total Applications"
            value={stats.totalApplications}
          />
          <StatCard
            title="Active Pipeline"
            value={stats.activePipeline}
          />
          <StatCard
            title="This Week"
            value={stats.thisWeek}
          />
          <StatCard
            title="Response Rate"
            value={`${stats.responseRate}%`}
          />
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <PipelineChart stats={stats} />
          <WeeklyChart stats={stats} />
        </div>

        {/* Recent Activity */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent Applications</CardTitle>
          </CardHeader>
          <CardContent>
            <ApplicationTable
              applications={recentApplications.slice(0, 5)}
              compact
            />
          </CardContent>
        </Card>
      </div>
    </>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { Header } from '@/components/layout/header';
import { ApplicationTable } from '@/components/applications/application-table';
import { fetchApplications } from '@/actions/applications';
import { Application } from '@/lib/types';
import { STATUSES, SOURCES, STATUS_LABELS, SOURCE_LABELS } from '@/lib/constants';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Search } from 'lucide-react';

export default function TablePage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [filteredApplications, setFilteredApplications] = useState<Application[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [sourceFilter, setSourceFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchApplications().then(setApplications);
  }, []);

  useEffect(() => {
    let filtered = applications;

    if (statusFilter) {
      filtered = filtered.filter((a) => a.status === statusFilter);
    }

    if (sourceFilter) {
      filtered = filtered.filter((a) => a.source === sourceFilter);
    }

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (a) =>
          a.company_name.toLowerCase().includes(query) ||
          a.role_title.toLowerCase().includes(query)
      );
    }

    setFilteredApplications(filtered);
  }, [applications, statusFilter, sourceFilter, searchQuery]);

  return (
    <>
      <Header title="Applications" />

      <div className="flex-1 overflow-auto p-6">
        {/* Filters */}
        <div className="flex gap-4 mb-6">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by company or role..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>

          <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value ?? '')}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">All statuses</SelectItem>
              {STATUSES.map((status) => (
                <SelectItem key={status} value={status}>
                  {STATUS_LABELS[status]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={sourceFilter} onValueChange={(value) => setSourceFilter(value ?? '')}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="All sources" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">All sources</SelectItem>
              {SOURCES.map((source) => (
                <SelectItem key={source} value={source}>
                  {SOURCE_LABELS[source]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Results count */}
        <p className="text-sm text-muted-foreground mb-4">
          {filteredApplications.length} application{filteredApplications.length !== 1 ? 's' : ''}
        </p>

        {/* Table */}
        <ApplicationTable applications={filteredApplications} />
      </div>
    </>
  );
}

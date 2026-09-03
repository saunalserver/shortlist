import { NextResponse } from 'next/server';
import { exportAllApplications } from '@/lib/db';
import { STATUS_LABELS, SOURCE_LABELS } from '@/lib/constants';

export async function GET() {
  const applications = exportAllApplications();

  const headers = [
    'Company',
    'Role',
    'Status',
    'Source',
    'Date Applied',
    'Location',
    'Salary',
    'Tags',
    'Notes',
    'Created At',
  ];

  const rows = applications.map((app) => [
    app.company_name,
    app.role_title,
    STATUS_LABELS[app.status],
    app.source ? SOURCE_LABELS[app.source] : '',
    app.date_applied || '',
    app.location || '',
    app.salary_info || '',
    app.tags.join('; '),
    app.notes?.replace(/\n/g, ' ') || '',
    app.created_at,
  ]);

  const csv = [
    headers.join(','),
    ...rows.map((row) =>
      row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')
    ),
  ].join('\n');

  const date = new Date().toISOString().split('T')[0];

  return new NextResponse(csv, {
    headers: {
      'Content-Type': 'text/csv',
      'Content-Disposition': `attachment; filename="jobsearch-export-${date}.csv"`,
    },
  });
}

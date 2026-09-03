import { NextResponse } from 'next/server';
import { exportAllApplications, exportAllCompanies } from '@/lib/db';

export async function GET() {
  const applications = exportAllApplications();
  const companies = exportAllCompanies();

  const data = {
    exportedAt: new Date().toISOString(),
    applications,
    companies
  };

  const date = new Date().toISOString().split('T')[0];

  return new NextResponse(JSON.stringify(data, null, 2), {
    headers: {
      'Content-Type': 'application/json',
      'Content-Disposition': `attachment; filename="jobsearch-export-${date}.json"`,
    },
  });
}

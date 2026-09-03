import { NextRequest, NextResponse } from 'next/server';
import { getAutojobJobById } from '@/lib/autojob-db';
import fs from 'fs';
import path from 'path';

const DATA_DIR = process.env.DATABASE_PATH ? path.dirname(process.env.DATABASE_PATH) : '/app/data';

export const dynamic = 'force-dynamic';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string; pdfName: string }> }
) {
  const { jobId, pdfName } = await params;

  const jobIdNum = parseInt(jobId, 10);
  if (isNaN(jobIdNum)) {
    return NextResponse.json({ error: 'Invalid job ID' }, { status: 400 });
  }

  const job = getAutojobJobById(jobIdNum);
  if (!job || !job.output_folder) {
    return NextResponse.json({ error: 'Job or output folder not found' }, { status: 404 });
  }

  // Only allow specific PDF file names
  const allowedNames = ['resume.pdf', 'cover_letter.pdf'];
  if (!allowedNames.includes(pdfName)) {
    return NextResponse.json({ error: 'Invalid file name' }, { status: 400 });
  }

  // Remap host output path to mounted source directory (works for any host checkout)
  const containerOutputBase = '/app/autojob-source/output';
  const pathMatch = job.output_folder.match(/output\/(.+)$/);
  const relativePath = pathMatch ? pathMatch[1] : job.output_folder.replace(/^\//, '');
  const filePath = path.join(containerOutputBase, relativePath, pdfName);

  if (!fs.existsSync(filePath)) {
    return NextResponse.json({ error: 'File not found at ' + filePath }, { status: 404 });
  }

  const fileBuffer = fs.readFileSync(filePath);

  return new NextResponse(fileBuffer, {
    headers: {
      'Content-Type': 'application/pdf',
      'Content-Disposition': `inline; filename="${pdfName}"`,
      'Content-Length': fileBuffer.length.toString(),
    },
  });
}

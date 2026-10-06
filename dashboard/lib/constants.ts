import { ApplicationStatus, ApplicationSource } from './types';

export const STATUSES: ApplicationStatus[] = [
  'bookmarked',
  'applied',
  'screening',
  'interview',
  'final_round',
  'offer',
  'accepted',
  'rejected',
  'withdrawn',
  'ghosted',
];

export const ACTIVE_STATUSES: ApplicationStatus[] = [
  'bookmarked',
  'applied',
  'screening',
  'interview',
  'final_round',
  'offer',
];

export const TERMINAL_STATUSES: ApplicationStatus[] = [
  'accepted',
  'rejected',
  'withdrawn',
  'ghosted',
];

export const KANBAN_STATUSES: ApplicationStatus[] = [
  'bookmarked',
  'applied',
  'screening',
  'interview',
  'final_round',
  'offer',
];

export const SOURCES: ApplicationSource[] = [
  'linkedin',
  'indeed',
  'wellfound',
  'referral',
  'cold_outreach',
  'recruiter',
  'other',
];

/** One-click status moves on the tracker table. */
export const QUICK_STATUSES: ApplicationStatus[] = [
  'screening',
  'interview',
  'offer',
  'rejected',
  'ghosted',
];

/** Optional reasons captured with every dismiss (jobs.dismiss_reason). Order = number keys 1-7. */
export const DISMISS_REASONS: { slug: string; label: string }[] = [
  { slug: 'role-family', label: 'role family' },
  { slug: 'seniority', label: 'seniority' },
  { slug: 'phone-field', label: 'phone / field' },
  { slug: 'commute-onsite', label: 'commute / onsite' },
  { slug: 'employer-type', label: 'employer type' },
  { slug: 'bad-data', label: 'bad data' },
  { slug: 'stale', label: 'stale' },
];

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  bookmarked: 'Bookmarked',
  applied: 'Applied',
  screening: 'Screening',
  interview: 'Interview',
  final_round: 'Final Round',
  offer: 'Offer',
  accepted: 'Accepted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  ghosted: 'Ghosted',
};

export const SOURCE_LABELS: Partial<Record<ApplicationSource, string>> = {
  linkedin: 'LinkedIn',
  indeed: 'Indeed',
  wellfound: 'Wellfound',
  referral: 'Referral',
  cold_outreach: 'Cold Outreach',
  recruiter: 'Recruiter',
  other: 'Other',
};

/** Known sources get their label; pipeline slugs pass through unchanged. */
export const sourceLabel = (s: string | null | undefined): string => (s ? SOURCE_LABELS[s] ?? s : '-');

export const COMPANY_SIZES = [
  '1-10',
  '10-50',
  '50-200',
  '200-500',
  '500-1000',
  '1000+',
];

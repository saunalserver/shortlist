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

export const SOURCE_LABELS: Record<ApplicationSource, string> = {
  linkedin: 'LinkedIn',
  indeed: 'Indeed',
  wellfound: 'Wellfound',
  referral: 'Referral',
  cold_outreach: 'Cold Outreach',
  recruiter: 'Recruiter',
  other: 'Other',
};

export const COMPANY_SIZES = [
  '1-10',
  '10-50',
  '50-200',
  '200-500',
  '500-1000',
  '1000+',
];

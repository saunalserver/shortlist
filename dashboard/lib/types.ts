export type ApplicationStatus =
  | 'bookmarked'
  | 'applied'
  | 'screening'
  | 'interview'
  | 'final_round'
  | 'offer'
  | 'accepted'
  | 'rejected'
  | 'withdrawn'
  | 'ghosted';

export type ApplicationSource =
  | 'linkedin'
  | 'indeed'
  | 'wellfound'
  | 'referral'
  | 'cold_outreach'
  | 'recruiter'
  | 'other';

export interface Application {
  id: string;
  company_name: string;
  role_title: string;
  date_applied: string | null;
  source: ApplicationSource | null;
  status: ApplicationStatus;
  posting_url: string | null;
  salary_info: string | null;
  location: string | null;
  notes: string | null;
  tags: string[];
  next_action: string | null;
  next_action_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface Company {
  id: string;
  name: string;
  website: string | null;
  size: string | null;
  industry: string | null;
  notes: string | null;
  watchlist: boolean;
  created_at: string;
}


export interface DashboardStats {
  totalApplications: number;
  activePipeline: number;
  thisWeek: number;
  responseRate: number;
  byStatus: Record<ApplicationStatus, number>;
  weeklyApplications: { week: string; count: number }[];
}

export interface ApplicationFilters {
  status?: ApplicationStatus;
  source?: ApplicationSource;
  search?: string;
}

// Input types for mutations
export interface CreateApplicationInput {
  company_name: string;
  role_title: string;
  date_applied?: string | null;
  source?: ApplicationSource | null;
  status?: ApplicationStatus;
  posting_url?: string | null;
  salary_info?: string | null;
  location?: string | null;
  notes?: string | null;
  tags?: string[];
  next_action?: string | null;
  next_action_date?: string | null;
}

export interface UpdateApplicationInput {
  company_name?: string;
  role_title?: string;
  date_applied?: string | null;
  source?: ApplicationSource | null;
  status?: ApplicationStatus;
  posting_url?: string | null;
  salary_info?: string | null;
  location?: string | null;
  notes?: string | null;
  tags?: string[];
  next_action?: string | null;
  next_action_date?: string | null;
}

export interface CreateCompanyInput {
  name: string;
  website?: string | null;
  size?: string | null;
  industry?: string | null;
  notes?: string | null;
  watchlist?: boolean;
}

export interface UpdateCompanyInput {
  name?: string;
  website?: string | null;
  size?: string | null;
  industry?: string | null;
  notes?: string | null;
  watchlist?: boolean;
}

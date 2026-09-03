'use server';

import {
  getApplications,
  getApplicationById,
  createApplication,
  updateApplication,
  deleteApplication,
  getStats,
} from '@/lib/db';
import {
  Application,
  CreateApplicationInput,
  UpdateApplicationInput,
  ApplicationFilters,
  DashboardStats,
} from '@/lib/types';

export async function fetchApplications(filters?: ApplicationFilters): Promise<Application[]> {
  return getApplications(filters);
}

export async function fetchApplication(id: string): Promise<Application | null> {
  return getApplicationById(id);
}

export async function createNewApplication(input: CreateApplicationInput): Promise<Application> {
  return createApplication(input);
}

export async function updateExistingApplication(
  id: string,
  input: UpdateApplicationInput
): Promise<Application | null> {
  return updateApplication(id, input);
}

export async function deleteApplicationById(id: string): Promise<boolean> {
  return deleteApplication(id);
}

export async function fetchStats(): Promise<DashboardStats> {
  return getStats();
}

'use server';

import {
  getCompanies,
  getCompanyById,
  createCompany,
  updateCompany,
  deleteCompany,
} from '@/lib/db';
import { Company, CreateCompanyInput, UpdateCompanyInput } from '@/lib/types';

export async function fetchCompanies(): Promise<Company[]> {
  return getCompanies();
}

export async function fetchCompany(id: string): Promise<Company | null> {
  return getCompanyById(id);
}

export async function createNewCompany(input: CreateCompanyInput): Promise<Company> {
  return createCompany(input);
}

export async function updateExistingCompany(
  id: string,
  input: UpdateCompanyInput
): Promise<Company | null> {
  return updateCompany(id, input);
}

export async function deleteCompanyById(id: string): Promise<boolean> {
  return deleteCompany(id);
}




'use client';

import { useEffect, useState } from 'react';
import { Header } from '@/components/layout/header';
import { CompanyList } from '@/components/companies/company-list';
import { CompanyForm } from '@/components/companies/company-form';
import { fetchCompanies } from '@/actions/companies';
import { Company } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingCompany, setEditingCompany] = useState<Company | null>(null);

  useEffect(() => {
    fetchCompanies().then(setCompanies);
  }, []);

  const handleEdit = (company: Company) => {
    setEditingCompany(company);
    setIsDialogOpen(true);
  };

  const handleSuccess = () => {
    setIsDialogOpen(false);
    setEditingCompany(null);
    fetchCompanies().then(setCompanies);
  };

  const handleClose = () => {
    setIsDialogOpen(false);
    setEditingCompany(null);
  };

  return (
    <>
      <Header title="Companies" />

      <div className="flex-1 overflow-auto p-6">
        <div className="mb-6">
          <Button onClick={() => setIsDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Add Company
          </Button>
        </div>

        <CompanyList companies={companies} onEdit={handleEdit} />
      </div>

      <Dialog open={isDialogOpen} onOpenChange={handleClose}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingCompany ? 'Edit Company' : 'Add Company'}
            </DialogTitle>
          </DialogHeader>
          <CompanyForm
            company={editingCompany}
            onSuccess={handleSuccess}
            onCancel={handleClose}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

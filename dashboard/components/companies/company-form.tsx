'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Company, CreateCompanyInput, UpdateCompanyInput } from '@/lib/types';
import { COMPANY_SIZES } from '@/lib/constants';
import { createNewCompany, updateExistingCompany } from '@/actions/companies';

interface CompanyFormProps {
  company?: Company | null;
  onSuccess: (company: Company) => void;
  onCancel?: () => void;
}

export function CompanyForm({ company, onSuccess, onCancel }: CompanyFormProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formData, setFormData] = useState({
    name: company?.name ?? '',
    website: company?.website ?? '',
    size: company?.size ?? '',
    industry: company?.industry ?? '',
    notes: company?.notes ?? '',
    watchlist: company?.watchlist ?? false,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      const data = {
        name: formData.name,
        website: formData.website || null,
        size: formData.size || null,
        industry: formData.industry || null,
        notes: formData.notes || null,
        watchlist: formData.watchlist,
      };

      if (company) {
        const result = await updateExistingCompany(company.id, data);
        if (result) onSuccess(result);
      } else {
        const result = await createNewCompany(data as CreateCompanyInput);
        onSuccess(result);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="name">Company Name *</Label>
        <Input
          id="name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="website">Website</Label>
        <Input
          id="website"
          type="url"
          value={formData.website}
          onChange={(e) => setFormData({ ...formData, website: e.target.value })}
          placeholder="https://..."
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="size">Size</Label>
          <Select
            value={formData.size || undefined}
            onValueChange={(value) => setFormData({ ...formData, size: value ?? '' })}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select size" />
            </SelectTrigger>
            <SelectContent>
              {COMPANY_SIZES.map((size) => (
                <SelectItem key={size} value={size}>
                  {size} employees
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="industry">Industry</Label>
          <Input
            id="industry"
            value={formData.industry}
            onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
            placeholder="e.g., SaaS, FinTech"
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="notes">Notes</Label>
        <Textarea
          id="notes"
          value={formData.notes}
          onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
          rows={3}
        />
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="watchlist"
          checked={formData.watchlist}
          onChange={(e) => setFormData({ ...formData, watchlist: e.target.checked })}
          className="rounded border-input"
        />
        <Label htmlFor="watchlist">Add to watchlist</Label>
      </div>

      <div className="flex justify-end gap-2 pt-4">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Saving...' : company ? 'Update' : 'Create'}
        </Button>
      </div>
    </form>
  );
}

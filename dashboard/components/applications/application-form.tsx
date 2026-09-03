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
import {
  Application,
  CreateApplicationInput,
  UpdateApplicationInput,
  ApplicationStatus,
  ApplicationSource,
} from '@/lib/types';
import { STATUSES, SOURCES, STATUS_LABELS, SOURCE_LABELS } from '@/lib/constants';
import { createNewApplication, updateExistingApplication } from '@/actions/applications';

interface ApplicationFormProps {
  application?: Application | null;
  onSuccess: (application: Application) => void;
  onCancel?: () => void;
}

export function ApplicationForm({ application, onSuccess, onCancel }: ApplicationFormProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formData, setFormData] = useState({
    company_name: application?.company_name ?? '',
    role_title: application?.role_title ?? '',
    date_applied: application?.date_applied ?? '',
    source: (application?.source ?? '') as string,
    status: (application?.status ?? 'bookmarked') as ApplicationStatus,
    posting_url: application?.posting_url ?? '',
    salary_info: application?.salary_info ?? '',
    location: application?.location ?? '',
    notes: application?.notes ?? '',
    tags: application?.tags?.join(', ') ?? '',
    next_action: application?.next_action ?? '',
    next_action_date: application?.next_action_date ?? '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      const data: UpdateApplicationInput = {
        company_name: formData.company_name,
        role_title: formData.role_title,
        date_applied: formData.date_applied || null,
        source: (formData.source || null) as ApplicationSource | null,
        status: formData.status,
        posting_url: formData.posting_url || null,
        salary_info: formData.salary_info || null,
        location: formData.location || null,
        notes: formData.notes || null,
        tags: formData.tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
        next_action: formData.next_action || null,
        next_action_date: formData.next_action_date || null,
      };

      if (application) {
        const result = await updateExistingApplication(application.id, data);
        if (result) onSuccess(result);
      } else {
        const result = await createNewApplication(data as CreateApplicationInput);
        onSuccess(result);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="company_name">Company *</Label>
          <Input
            id="company_name"
            value={formData.company_name}
            onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
            required
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="role_title">Role *</Label>
          <Input
            id="role_title"
            value={formData.role_title}
            onChange={(e) => setFormData({ ...formData, role_title: e.target.value })}
            required
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="status">Status</Label>
          <Select
            value={formData.status}
            onValueChange={(value) => setFormData({ ...formData, status: value as ApplicationStatus })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUSES.map((status) => (
                <SelectItem key={status} value={status}>
                  {STATUS_LABELS[status]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="source">Source</Label>
          <Select
            value={formData.source || undefined}
            onValueChange={(value) => setFormData({ ...formData, source: value ?? '' })}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select source" />
            </SelectTrigger>
            <SelectContent>
              {SOURCES.map((source) => (
                <SelectItem key={source} value={source}>
                  {SOURCE_LABELS[source]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="date_applied">Date Applied</Label>
          <Input
            id="date_applied"
            type="date"
            value={formData.date_applied}
            onChange={(e) => setFormData({ ...formData, date_applied: e.target.value })}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="location">Location</Label>
          <Input
            id="location"
            value={formData.location}
            onChange={(e) => setFormData({ ...formData, location: e.target.value })}
            placeholder="e.g., Vancouver or Remote"
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="posting_url">Job Posting URL</Label>
        <Input
          id="posting_url"
          type="url"
          value={formData.posting_url}
          onChange={(e) => setFormData({ ...formData, posting_url: e.target.value })}
          placeholder="https://..."
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="salary_info">Salary Info</Label>
          <Input
            id="salary_info"
            value={formData.salary_info}
            onChange={(e) => setFormData({ ...formData, salary_info: e.target.value })}
            placeholder="e.g., $80K-$100K"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="tags">Tags (comma-separated)</Label>
          <Input
            id="tags"
            value={formData.tags}
            onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
            placeholder="hot, referral, dream company"
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="next_action">Next Action</Label>
        <Input
          id="next_action"
          value={formData.next_action}
          onChange={(e) => setFormData({ ...formData, next_action: e.target.value })}
          placeholder="e.g., Follow up on application"
        />
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

      <div className="flex justify-end gap-2 pt-4">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Saving...' : application ? 'Update' : 'Create'}
        </Button>
      </div>
    </form>
  );
}

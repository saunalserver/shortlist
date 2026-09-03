'use client';

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Application } from '@/lib/types';
import { ApplicationForm } from './application-form';
import { useUIStore } from '@/store/ui-store';
import { useRouter } from 'next/navigation';

export function QuickAddDialog() {
  const router = useRouter();
  const { isQuickAddOpen, closeQuickAdd } = useUIStore();

  const handleSuccess = (application: Application) => {
    closeQuickAdd();
    router.refresh();
  };

  return (
    <Dialog open={isQuickAddOpen} onOpenChange={(open) => !open && closeQuickAdd()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add Application</DialogTitle>
        </DialogHeader>
        <ApplicationForm
          onSuccess={handleSuccess}
          onCancel={closeQuickAdd}
        />
      </DialogContent>
    </Dialog>
  );
}

import { Badge } from '@/components/ui/badge';
import { ApplicationStatus } from '@/lib/types';
import { STATUS_LABELS } from '@/lib/constants';
import { cn } from '@/lib/utils';

const statusColors: Record<ApplicationStatus, string> = {
  bookmarked: 'bg-[rgba(90,111,138,0.15)] text-[#5a6f8a] border-[rgba(90,111,138,0.2)]',
  applied: 'bg-[rgba(56,189,248,0.12)] text-[#38bdf8] border-[rgba(56,189,248,0.2)]',
  screening: 'bg-[rgba(232,163,23,0.12)] text-[#e8a317] border-[rgba(232,163,23,0.2)]',
  interview: 'bg-[rgba(251,146,60,0.12)] text-[#fb923c] border-[rgba(251,146,60,0.2)]',
  final_round: 'bg-[rgba(167,139,250,0.12)] text-[#a78bfa] border-[rgba(167,139,250,0.2)]',
  offer: 'bg-[rgba(34,197,94,0.12)] text-[#22c55e] border-[rgba(34,197,94,0.2)]',
  accepted: 'bg-[rgba(34,197,94,0.2)] text-[#22c55e] border-[rgba(34,197,94,0.3)]',
  rejected: 'bg-[rgba(239,68,68,0.12)] text-[#ef4444] border-[rgba(239,68,68,0.2)]',
  withdrawn: 'bg-[rgba(90,111,138,0.12)] text-[#5a6f8a] border-[rgba(90,111,138,0.2)]',
  ghosted: 'bg-[rgba(90,111,138,0.08)] text-[#5a6f8a] border-[rgba(90,111,138,0.15)]',
};

interface StatusBadgeProps {
  status: ApplicationStatus;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <Badge variant="secondary" className={cn('border', statusColors[status], className)}>
      {STATUS_LABELS[status]}
    </Badge>
  );
}

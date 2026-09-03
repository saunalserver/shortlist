import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface StatCardProps {
  title: string;
  value: string | number;
  description?: string;
  className?: string;
  color?: string;
}

export function StatCard({ title, value, description, className, color = '#e8a317' }: StatCardProps) {
  return (
    <Card className={cn('border-t-2', className)} style={{ borderTopColor: color }}>
      <CardContent className="pt-6">
        <p className="text-sm font-medium text-[#5a6f8a]">{title}</p>
        <p className="text-3xl font-bold mt-1 text-[#d4dce8]">{value}</p>
        {description && (
          <p className="text-xs text-[#5a6f8a] mt-1">{description}</p>
        )}
      </CardContent>
    </Card>
  );
}

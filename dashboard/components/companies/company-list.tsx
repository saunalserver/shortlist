'use client';

import { Company } from '@/lib/types';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ExternalLink, Pencil, Trash2, Star } from 'lucide-react';
import { deleteCompanyById } from '@/actions/companies';
import { useRouter } from 'next/navigation';

interface CompanyListProps {
  companies: Company[];
  onEdit: (company: Company) => void;
}

export function CompanyList({ companies, onEdit }: CompanyListProps) {
  const router = useRouter();

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this company?')) return;
    await deleteCompanyById(id);
    router.refresh();
  };

  if (companies.length === 0) {
    return (
      <div className="text-center text-muted-foreground py-8">
        No companies yet. Add companies you&apos;re interested in.
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      {companies.map((company) => (
        <Card key={company.id}>
          <CardContent className="p-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-medium">{company.name}</h3>
                  {company.watchlist && (
                    <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1 text-sm text-muted-foreground">
                  {company.size && <span>{company.size}</span>}
                  {company.industry && <span>• {company.industry}</span>}
                </div>
                {company.notes && (
                  <p className="text-sm text-muted-foreground mt-2">{company.notes}</p>
                )}
              </div>

              <div className="flex items-center gap-1">
                {company.website && (
                  <a
                    href={company.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground h-9 w-9"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
                <Button variant="ghost" size="icon" onClick={() => onEdit(company)}>
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleDelete(company.id)}
                  className="text-destructive hover:text-destructive"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

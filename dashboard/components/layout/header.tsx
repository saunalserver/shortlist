'use client';

import { Button } from '@/components/ui/button';
import { Plus, Download } from 'lucide-react';
import { useUIStore } from '@/store/ui-store';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface HeaderProps {
  title: string;
}

export function Header({ title }: HeaderProps) {
  const openQuickAdd = useUIStore((state) => state.openQuickAdd);

  return (
    <header className="h-16 border-b bg-[#0b1120] border-[#1a2744] flex items-center justify-between px-6">
      <h2 className="text-lg font-semibold text-[#d4dce8]">{title}</h2>

      <div className="flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="outline" size="sm" />}>
            <Download className="h-4 w-4 mr-2" />
            Export
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem>
              <a href="/api/export/json" className="w-full">Export as JSON</a>
            </DropdownMenuItem>
            <DropdownMenuItem>
              <a href="/api/export/csv" className="w-full">Export as CSV</a>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Button onClick={openQuickAdd} size="sm" className="bg-[#e8a317] text-[#060a12] hover:bg-[#d4930f]">
          <Plus className="h-4 w-4 mr-2" />
          Add Application
        </Button>
      </div>
    </header>
  );
}

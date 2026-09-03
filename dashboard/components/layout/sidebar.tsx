'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  KanbanSquare,
  Table,
  Building2,
  Activity,
  List,
  Settings,
  FileText,
} from 'lucide-react';

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/kanban', label: 'Kanban', icon: KanbanSquare },
  { href: '/table', label: 'Table', icon: Table },
  { href: '/companies', label: 'Companies', icon: Building2 },
];

const pipelineItems = [
  { href: '/pipeline', label: 'Pipeline', icon: Activity },
  { href: '/pipeline/jobs', label: 'Review queue', icon: List },
  { href: '/pipeline/sources', label: 'Sources & config', icon: Settings },
  { href: '/pipeline/logs', label: 'Logs', icon: FileText },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r bg-[#0b1120] border-[#1a2744] flex flex-col">
      <div className="p-6 border-b border-[#1a2744]">
        <h1 className="text-xl font-bold text-[#e8a317]">Autojob</h1>
        <p className="text-xs text-[#5a6f8a] mt-1">Command Center</p>
      </div>

      <nav className="flex-1 p-4 space-y-1 overflow-auto">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                isActive
                  ? 'bg-[rgba(232,163,23,0.12)] text-[#e8a317] border border-[rgba(232,163,23,0.2)]'
                  : 'text-[#5a6f8a] hover:bg-[#111b2e] hover:text-[#d4dce8] border border-transparent'
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}

        <div className="pt-4 pb-2">
          <div className="h-px bg-[#1a2744]" />
        </div>

        <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-[#5a6f8a]">
          Pipeline
        </p>

        {pipelineItems.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                isActive
                  ? 'bg-[rgba(232,163,23,0.12)] text-[#e8a317] border border-[rgba(232,163,23,0.2)]'
                  : 'text-[#5a6f8a] hover:bg-[#111b2e] hover:text-[#d4dce8] border border-transparent'
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-[#1a2744] text-[10px] text-[#5a6f8a]">
        Daily run 07:00 · digest on Telegram
      </div>
    </aside>
  );
}

import { create } from 'zustand';

interface UIState {
  // Application panel
  selectedApplicationId: string | null;
  isPanelOpen: boolean;
  openPanel: (applicationId: string) => void;
  closePanel: () => void;

  // Quick add modal
  isQuickAddOpen: boolean;
  openQuickAdd: () => void;
  closeQuickAdd: () => void;

  // Table filters
  statusFilter: string | null;
  sourceFilter: string | null;
  searchQuery: string;
  setStatusFilter: (status: string | null) => void;
  setSourceFilter: (source: string | null) => void;
  setSearchQuery: (query: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  // Application panel
  selectedApplicationId: null,
  isPanelOpen: false,
  openPanel: (applicationId) =>
    set({ selectedApplicationId: applicationId, isPanelOpen: true }),
  closePanel: () => set({ isPanelOpen: false, selectedApplicationId: null }),

  // Quick add
  isQuickAddOpen: false,
  openQuickAdd: () => set({ isQuickAddOpen: true }),
  closeQuickAdd: () => set({ isQuickAddOpen: false }),

  // Filters
  statusFilter: null,
  sourceFilter: null,
  searchQuery: '',
  setStatusFilter: (status) => set({ statusFilter: status || null }),
  setSourceFilter: (source) => set({ sourceFilter: source || null }),
  setSearchQuery: (query) => set({ searchQuery: query }),
}));

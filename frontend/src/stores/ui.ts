"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

type UIState = {
  sidebarCollapsed: boolean;
  mobileNavOpen: boolean;
  commandOpen: boolean;
  activeProjectId: string | null;
  inspectorOpen: boolean;
  toggleSidebar: () => void;
  setMobileNav: (open: boolean) => void;
  setCommand: (open: boolean) => void;
  setProject: (id: string | null) => void;
  setInspector: (open: boolean) => void;
};

export const useUI = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      mobileNavOpen: false,
      commandOpen: false,
      activeProjectId: null,
      inspectorOpen: true,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setMobileNav: (open) => set({ mobileNavOpen: open }),
      setCommand: (open) => set({ commandOpen: open }),
      setProject: (id) => set({ activeProjectId: id }),
      setInspector: (open) => set({ inspectorOpen: open }),
    }),
    {
      name: "nexus-ui",
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, activeProjectId: s.activeProjectId, inspectorOpen: s.inspectorOpen }),
    },
  ),
);

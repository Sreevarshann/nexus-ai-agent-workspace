"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Loader2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import { CommandPalette } from "@/components/shell/command-palette";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { ApiError } from "@/lib/api";
import { useMe } from "@/lib/queries";
import { useUI } from "@/stores/ui";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const me = useMe();
  const mobileOpen = useUI((s) => s.mobileNavOpen);
  const setMobile = useUI((s) => s.setMobileNav);

  React.useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [me.error, router, pathname]);

  if (me.isPending || (me.error instanceof ApiError && me.error.status === 401)) {
    return (
      <div className="flex h-screen items-center justify-center bg-bg" aria-busy="true">
        <Loader2 className="size-5 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-bg">
      <div className="hidden md:block">
        <Sidebar />
      </div>
      <DialogPrimitive.Root open={mobileOpen} onOpenChange={setMobile}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-[rgb(15_23_42/0.35)] md:hidden" />
          <DialogPrimitive.Content className="fixed inset-y-0 left-0 z-50 shadow-pop md:hidden" aria-label="Navigation">
            <DialogPrimitive.Title className="sr-only">Navigation</DialogPrimitive.Title>
            <DialogPrimitive.Description className="sr-only">Primary navigation</DialogPrimitive.Description>
            <Sidebar mobile />
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="nx-scroll min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
      <CommandPalette />
    </div>
  );
}

"use client";

import { ChevronsLeft, ChevronsRight, MessageSquareText, Pin, Plus } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Wordmark } from "@/components/shell/logo";
import { NAV, SETTINGS_NAV, type NavItem } from "@/components/shell/nav";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/overlay";
import { useConversations, useProjects } from "@/lib/queries";
import { cn, timeAgo } from "@/lib/utils";
import { useUI } from "@/stores/ui";

export function Sidebar({ mobile = false }: { mobile?: boolean }) {
  const collapsedPref = useUI((s) => s.sidebarCollapsed);
  const collapsed = mobile ? false : collapsedPref;
  const toggle = useUI((s) => s.toggleSidebar);
  const setMobile = useUI((s) => s.setMobileNav);
  const setProject = useUI((s) => s.setProject);
  const pathname = usePathname();
  const router = useRouter();
  const { data: conversations } = useConversations();
  const { data: projects } = useProjects();
  const pinned = projects?.filter((p) => p.pinned) ?? [];

  const go = (href: string) => {
    router.push(href);
    if (mobile) setMobile(false);
  };

  return (
    <aside
      className={cn(
        "flex h-full flex-col border-r border-line bg-surface/80 backdrop-blur-sm transition-[width] duration-200",
        collapsed ? "w-[68px]" : "w-[264px]",
      )}
      aria-label="Primary"
    >
      <div className={cn("flex h-16 items-center", collapsed ? "justify-center" : "justify-between px-4")}>
        <Link href="/workspace" aria-label="NEXUS AI home" onClick={() => mobile && setMobile(false)}>
          <Wordmark collapsed={collapsed} />
        </Link>
        {!collapsed && !mobile && (
          <Tooltip content={<span>Collapse <Kbd className="ml-1 border-white/20 bg-white/10 text-white">⌘\</Kbd></span>}>
            <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label="Collapse sidebar">
              <ChevronsLeft />
            </Button>
          </Tooltip>
        )}
      </div>

      <div className={cn("pb-3", collapsed ? "px-3" : "px-4")}>
        <Tooltip content="Start a new mission" side="right">
          <Button className={cn("w-full", collapsed && "px-0")} onClick={() => go("/workspace?new=1")} aria-label="New mission">
            <Plus />
            {!collapsed && "New mission"}
          </Button>
        </Tooltip>
      </div>

      <nav className={cn("nx-scroll flex-1 overflow-y-auto", collapsed ? "px-3" : "px-3")}>
        <ul className="space-y-0.5">
          {NAV.map((item) => (
            <NavLink key={item.href} item={item} active={pathname.startsWith(item.href)} collapsed={collapsed} onNavigate={go} />
          ))}
        </ul>

        {!collapsed && pinned.length > 0 && (
          <Section title="Pinned projects">
            {pinned.map((p) => (
              <button
                key={p.id}
                onClick={() => {
                  setProject(p.id);
                  go("/workspace");
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] text-ink-2 hover:bg-bg-subtle"
              >
                <Pin className="size-3.5 text-primary" />
                <span className="truncate">{p.name}</span>
              </button>
            ))}
          </Section>
        )}

        {!collapsed && (
          <Section title="Recent sessions">
            {(conversations ?? []).slice(0, 7).map((c) => {
              const active = pathname === `/workspace/${c.id}`;
              return (
                <button
                  key={c.id}
                  onClick={() => go(`/workspace/${c.id}`)}
                  className={cn(
                    "group flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition",
                    active ? "bg-primary-soft text-primary-deep" : "text-ink-2 hover:bg-bg-subtle",
                  )}
                >
                  <MessageSquareText className={cn("size-3.5 shrink-0", active ? "text-primary" : "text-faint")} />
                  <span className="min-w-0 flex-1 truncate">{c.title}</span>
                  <span className="shrink-0 text-[11px] text-faint opacity-0 transition group-hover:opacity-100">{timeAgo(c.updated_at)}</span>
                </button>
              );
            })}
            {conversations?.length === 0 && <p className="px-2.5 py-1 text-[12.5px] text-faint">No conversations yet</p>}
          </Section>
        )}
      </nav>

      <div className={cn("border-t border-line py-3", collapsed ? "px-3" : "px-3")}>
        <ul>
          <NavLink item={SETTINGS_NAV} active={pathname.startsWith("/settings")} collapsed={collapsed} onNavigate={go} />
        </ul>
        {collapsed && !mobile && (
          <Tooltip content="Expand sidebar" side="right">
            <Button variant="ghost" size="icon" className="mt-1 w-full" onClick={toggle} aria-label="Expand sidebar">
              <ChevronsRight />
            </Button>
          </Tooltip>
        )}
      </div>
    </aside>
  );
}

function NavLink({ item, active, collapsed, onNavigate }: { item: NavItem; active: boolean; collapsed: boolean; onNavigate: (h: string) => void }) {
  const inner = (
    <a
      href={item.href}
      onClick={(e) => {
        e.preventDefault();
        onNavigate(item.href);
      }}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative flex h-9 items-center gap-3 rounded-[10px] text-[13.5px] font-medium transition",
        collapsed ? "justify-center" : "px-2.5",
        active ? "bg-primary-soft text-primary-deep" : "text-ink-2 hover:bg-bg-subtle hover:text-ink",
      )}
    >
      {active && <span className="absolute -left-3 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-primary" />}
      <item.icon className={cn("size-[18px] shrink-0", active ? "text-primary" : "text-muted")} />
      {!collapsed && <span className="truncate">{item.label}</span>}
    </a>
  );
  return <li>{collapsed ? <Tooltip content={item.label} side="right">{inner}</Tooltip> : inner}</li>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-6">
      <div className="mb-1.5 px-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-faint">{title}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

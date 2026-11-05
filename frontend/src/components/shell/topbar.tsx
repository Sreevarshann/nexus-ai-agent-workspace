"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bell, Bot, ChevronDown, Cpu, FolderKanban, LogOut, Menu, Plus, Search, Settings, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { NAV, SETTINGS_NAV } from "@/components/shell/nav";
import { Kbd } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusDot } from "@/components/ui/status";
import {
  Dialog,
  DialogContent,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Tooltip,
} from "@/components/ui/overlay";
import { api } from "@/lib/api";
import { useHealth, useMe, useProjects, useTasks } from "@/lib/queries";
import { cn, timeAgo } from "@/lib/utils";
import { useUI } from "@/stores/ui";

export function Topbar() {
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const setCommand = useUI((s) => s.setCommand);
  const setMobile = useUI((s) => s.setMobileNav);
  const activeProjectId = useUI((s) => s.activeProjectId);
  const setProject = useUI((s) => s.setProject);
  const { data: me } = useMe();
  const { data: projects } = useProjects();
  const { data: health } = useHealth();
  const { data: tasks } = useTasks();

  const section = [...NAV, SETTINGS_NAV].find((n) => pathname.startsWith(n.href));
  const project = projects?.find((p) => p.id === activeProjectId) ?? projects?.[0];
  const llm = health?.checks.llm;
  const active = tasks?.filter((t) => ["queued", "running", "waiting_approval", "paused"].includes(t.status)) ?? [];
  const recentDone = tasks?.filter((t) => ["completed", "failed", "cancelled"].includes(t.status)).slice(0, 6) ?? [];

  const logout = async () => {
    await api.post("/auth/logout");
    qc.clear();
    router.replace("/login");
  };

  const [newOpen, setNewOpen] = React.useState(false);
  const [newName, setNewName] = React.useState("");
  const createProject = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      const p = await api.post<{ id: string }>("/projects", { name });
      await qc.invalidateQueries({ queryKey: ["projects"] });
      setProject(p.id);
      setNewOpen(false);
      setNewName("");
      toast.success(`Project “${name}” created`);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <>
    <Dialog open={newOpen} onOpenChange={setNewOpen}>
      <DialogContent title="New project" description="Projects group conversations, documents, datasets and artifacts.">
        <form onSubmit={(e) => { e.preventDefault(); void createProject(); }} className="space-y-4">
          <Input autoFocus aria-label="Project name" placeholder="e.g. Market research" value={newName} onChange={(e) => setNewName(e.target.value)} />
          <div className="flex justify-end"><Button type="submit" disabled={!newName.trim()}>Create project</Button></div>
        </form>
      </DialogContent>
    </Dialog>
    <header className="flex h-16 shrink-0 items-center gap-3 border-b border-line bg-surface/85 px-4 backdrop-blur-md md:px-6">
      <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setMobile(true)} aria-label="Open navigation">
        <Menu />
      </Button>

      <div className="flex min-w-0 items-center gap-1.5 text-[13px]">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex min-w-0 items-center gap-1.5 rounded-lg px-2 py-1.5 font-medium text-ink hover:bg-bg-subtle" aria-label="Switch project">
              <FolderKanban className="size-4 text-primary" />
              <span className="max-w-[140px] truncate">{project?.name ?? "Workspace"}</span>
              <ChevronDown className="size-3.5 text-muted" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Projects</DropdownMenuLabel>
            {projects?.map((p) => (
              <DropdownMenuItem key={p.id} onSelect={() => setProject(p.id)}>
                <FolderKanban />
                <span className="flex-1 truncate">{p.name}</span>
                {p.id === project?.id && <span className="size-1.5 rounded-full bg-primary" />}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setNewOpen(true)}>
              <Plus /> New project
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {section && (
          <>
            <span className="text-faint">/</span>
            <span className="hidden truncate text-muted sm:inline">{section.label}</span>
          </>
        )}
      </div>

      <button
        onClick={() => setCommand(true)}
        className="ml-auto hidden h-9 w-full max-w-[340px] items-center gap-2 rounded-[10px] border border-line bg-surface-2 px-3 text-[13px] text-faint transition hover:border-line-strong md:flex"
        aria-label="Open command palette"
      >
        <Search className="size-4" />
        <span className="flex-1 text-left">Search or run a command…</span>
        <Kbd>⌘K</Kbd>
      </button>

      <div className="ml-auto flex items-center gap-1.5 md:ml-0">
        <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setCommand(true)} aria-label="Search">
          <Search />
        </Button>

        <Tooltip
          content={
            llm ? (
              <div className="space-y-0.5">
                <div>{llm.ok ? "Model online" : "Model unavailable"} · {String(llm.provider)}</div>
                {llm.error ? <div className="opacity-80">{String(llm.error)}</div> : null}
                <div className="opacity-70">{llm.latency_ms} ms health check</div>
              </div>
            ) : (
              "Checking model…"
            )
          }
        >
          <Link href="/settings" className="hidden h-9 items-center gap-2 rounded-[10px] border border-line bg-surface px-2.5 text-[12.5px] font-medium text-ink-2 shadow-sm hover:border-line-strong lg:flex">
            <Cpu className="size-3.5 text-muted" />
            <span className="max-w-[150px] truncate">{llm ? String(llm.model) : "…"}</span>
            <StatusDot ok={llm ? llm.ok : null} />
          </Link>
        </Tooltip>

        <Tooltip content={active.length ? `${active.length} active task${active.length > 1 ? "s" : ""}` : "No agents running"}>
          <Link
            href="/missions"
            className={cn(
              "flex h-9 items-center gap-1.5 rounded-[10px] px-2.5 text-[12.5px] font-medium transition",
              active.length ? "bg-primary-soft text-primary-deep" : "text-muted hover:bg-bg-subtle",
            )}
            aria-label="Agent activity"
          >
            <Bot className={cn("size-4", active.some((t) => t.status === "running") && "animate-pulse")} />
            <span className="tabular-nums">{active.length}</span>
          </Link>
        </Tooltip>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Notifications" className="relative">
              <Bell />
              {active.some((t) => t.status === "waiting_approval") && (
                <span className="absolute right-2 top-2 size-2 rounded-full bg-warning ring-2 ring-surface" />
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-80">
            <DropdownMenuLabel>Task activity</DropdownMenuLabel>
            {[...active, ...recentDone].slice(0, 8).map((t) => (
              <DropdownMenuItem key={t.id} onSelect={() => router.push(`/missions/${t.id}`)} className="items-start">
                <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", {
                  "bg-primary": t.status === "running" || t.status === "queued",
                  "bg-warning": t.status === "waiting_approval" || t.status === "paused",
                  "bg-success": t.status === "completed",
                  "bg-danger": t.status === "failed",
                  "bg-faint": t.status === "cancelled",
                })} />
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-1 text-ink">{t.title}</span>
                  <span className="text-[11.5px] text-faint">{t.status.replace("_", " ")} · {timeAgo(t.finished_at ?? t.created_at)}</span>
                </span>
              </DropdownMenuItem>
            ))}
            {!tasks?.length && <div className="px-2.5 py-3 text-[12.5px] text-faint">No missions yet.</div>}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex size-9 items-center justify-center rounded-full bg-gradient-to-br from-[#dbe7ff] to-[#c7d8ff] text-[13px] font-semibold text-primary-deep ring-1 ring-[#c7d6fb]" aria-label="Account menu">
              {me?.name?.[0]?.toUpperCase() ?? <UserRound className="size-4" />}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <div className="px-2.5 py-2">
              <div className="text-[13px] font-medium text-ink">{me?.name}</div>
              <div className="text-[12px] text-muted">{me?.email}</div>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => router.push("/settings")}><Settings /> Settings</DropdownMenuItem>
            <DropdownMenuItem onSelect={logout}><LogOut /> Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
    </>
  );
}

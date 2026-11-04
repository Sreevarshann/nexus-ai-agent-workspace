"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { Activity, FileText, MessageSquarePlus, PanelLeft, Search, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { NAV, SETTINGS_NAV } from "@/components/shell/nav";
import { Kbd } from "@/components/ui/badge";
import { useArtifacts, useConversations, useTasks } from "@/lib/queries";
import { useUI } from "@/stores/ui";

export function CommandPalette() {
  const open = useUI((s) => s.commandOpen);
  const setOpen = useUI((s) => s.setCommand);
  const toggleSidebar = useUI((s) => s.toggleSidebar);
  const router = useRouter();
  const { data: conversations } = useConversations();
  const { data: tasks } = useTasks(undefined, false);
  const { data: artifacts } = useArtifacts();

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!useUI.getState().commandOpen);
      } else if (mod && e.key === "\\") {
        e.preventDefault();
        toggleSidebar();
      } else if (mod && e.altKey && /^[1-9]$/.test(e.key)) {
        const item = [...NAV, SETTINGS_NAV].find((n) => n.shortcut === e.key);
        if (item) {
          e.preventDefault();
          router.push(item.href);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, setOpen, toggleSidebar]);

  const run = (fn: () => void) => {
    setOpen(false);
    fn();
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-[rgb(15_23_42/0.3)] backdrop-blur-[2px]" />
        <DialogPrimitive.Content className="fixed left-1/2 top-[14vh] z-50 w-[calc(100vw-2rem)] max-w-[620px] -translate-x-1/2 overflow-hidden rounded-2xl border border-line bg-surface shadow-pop focus:outline-none">
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">Search pages, conversations, missions and actions</DialogPrimitive.Description>
          <Command label="Command palette" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-faint">
            <div className="flex items-center gap-2.5 border-b border-line px-4">
              <Search className="size-4 text-muted" />
              <Command.Input autoFocus placeholder="Type a command or search…" className="h-13 flex-1 bg-transparent py-4 text-[14.5px] text-ink outline-none placeholder:text-faint" />
              <Kbd>esc</Kbd>
            </div>
            <Command.List className="nx-scroll max-h-[420px] overflow-y-auto p-2">
              <Command.Empty className="py-10 text-center text-[13px] text-muted">No results.</Command.Empty>
              <Command.Group heading="Actions">
                <Item icon={MessageSquarePlus} onSelect={() => run(() => router.push("/workspace?new=1"))} hint="New">New conversation</Item>
                <Item icon={Activity} onSelect={() => run(() => router.push("/research"))}>Start a research mission</Item>
                <Item icon={Upload} onSelect={() => run(() => router.push("/library?upload=1"))}>Upload documents</Item>
                <Item icon={PanelLeft} onSelect={() => run(toggleSidebar)} hint="⌘\">Toggle sidebar</Item>
              </Command.Group>
              <Command.Group heading="Navigate">
                {[...NAV, SETTINGS_NAV].map((n) => (
                  <Item key={n.href} icon={n.icon} onSelect={() => run(() => router.push(n.href))} hint={n.shortcut ? `⌥⌘${n.shortcut}` : undefined} keywords={[n.description]}>
                    {n.label}
                  </Item>
                ))}
              </Command.Group>
              {!!conversations?.length && (
                <Command.Group heading="Conversations">
                  {conversations.slice(0, 8).map((c) => (
                    <Item key={c.id} icon={MessageSquarePlus} onSelect={() => run(() => router.push(`/workspace/${c.id}`))} value={`conversation ${c.title} ${c.id}`}>
                      {c.title}
                    </Item>
                  ))}
                </Command.Group>
              )}
              {!!tasks?.length && (
                <Command.Group heading="Missions">
                  {tasks.slice(0, 6).map((t) => (
                    <Item key={t.id} icon={Activity} onSelect={() => run(() => router.push(`/missions/${t.id}`))} value={`mission ${t.title} ${t.id}`} hint={t.status.replace("_", " ")}>
                      {t.title}
                    </Item>
                  ))}
                </Command.Group>
              )}
              {!!artifacts?.length && (
                <Command.Group heading="Artifacts">
                  {artifacts.slice(0, 6).map((a) => (
                    <Item key={a.id} icon={FileText} onSelect={() => run(() => router.push(`/artifacts/${a.id}`))} value={`artifact ${a.title} ${a.id}`}>
                      {a.title}
                    </Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function Item({
  icon: Icon,
  children,
  onSelect,
  hint,
  value,
  keywords,
}: {
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  onSelect: () => void;
  hint?: string;
  value?: string;
  keywords?: string[];
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      value={value}
      keywords={keywords}
      className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-[13.5px] text-ink-2 data-[selected=true]:bg-primary-soft data-[selected=true]:text-primary-deep"
    >
      <Icon className="size-4 shrink-0 text-muted" />
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {hint && <span className="text-[11.5px] text-faint">{hint}</span>}
    </Command.Item>
  );
}

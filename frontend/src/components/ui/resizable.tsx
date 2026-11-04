"use client";

import { Group, Panel, Separator, useDefaultLayout } from "react-resizable-panels";

import { cn } from "@/lib/utils";

export { Panel };

export function ResizableGroup({
  id,
  className,
  children,
  orientation = "horizontal",
}: {
  id: string;
  className?: string;
  children: React.ReactNode;
  orientation?: "horizontal" | "vertical";
}) {
  const storage = typeof window === "undefined" ? undefined : window.localStorage;
  const { defaultLayout, onLayoutChanged } = useDefaultLayout({ id: `nexus-${id}`, storage });
  return (
    <Group id={id} orientation={orientation} defaultLayout={defaultLayout} onLayoutChanged={onLayoutChanged} className={cn("h-full", className)}>
      {children}
    </Group>
  );
}

export function ResizeHandle({ className }: { className?: string }) {
  return (
    <Separator
      className={cn(
        "group relative w-px bg-line outline-none transition-colors data-[separator=active]:bg-primary data-[separator=hover]:bg-primary/60",
        className,
      )}
    >
      <span className="absolute inset-y-0 -left-1.5 -right-1.5" />
    </Separator>
  );
}

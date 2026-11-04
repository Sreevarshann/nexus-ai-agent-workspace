"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { api } from "@/lib/api";
import { subscribe } from "@/lib/sse";
import type { TaskDetail, TaskEvent } from "@/lib/types";

/** Task detail + live event stream. On reconnect, the stream resumes after the last seen event id. */
export function useTaskLive(taskId: string) {
  const qc = useQueryClient();
  const detail = useQuery({ queryKey: ["task-detail", taskId], queryFn: () => api.get<TaskDetail>(`/tasks/${taskId}/detail`) });
  const [live, setLive] = React.useState<TaskEvent[]>([]);
  const [draft, setDraft] = React.useState("");
  const [connection, setConnection] = React.useState("idle");
  const loaded = !!detail.data;
  const status = detail.data?.task.status;
  const lastId = detail.data?.events.at(-1)?.id;
  const lastIdRef = React.useRef<number | undefined>(undefined);
  React.useEffect(() => {
    lastIdRef.current = lastId;
  }, [lastId]);

  const terminal = status === "completed" || status === "failed" || status === "cancelled";

  React.useEffect(() => {
    if (!loaded || terminal) return;
    let refetchTimer: ReturnType<typeof setTimeout> | undefined;
    const refetchSoon = () => {
      clearTimeout(refetchTimer);
      refetchTimer = setTimeout(() => void qc.invalidateQueries({ queryKey: ["task-detail", taskId] }), 400);
    };
    const unsub = subscribe(`/api/tasks/${taskId}/events`, {
      lastEventId: lastIdRef.current ? String(lastIdRef.current) : undefined,
      onStatus: setConnection,
      onEvent: ({ event, data }) => {
        if (event === "task_event") {
          const ev = data as TaskEvent;
          setLive((xs) => (xs.some((x) => x.id === ev.id) ? xs : [...xs, ev]));
          if (ev.node === "synthesizer" && ev.type === "node_started") setDraft("");
          refetchSoon();
        } else if (event === "draft") {
          setDraft((d) => d + String((data as { delta?: string }).delta ?? ""));
        } else if (event === "status") {
          refetchSoon();
          void qc.invalidateQueries({ queryKey: ["tasks"] });
        }
      },
      stopOn: (e) => e.event === "status" && ["completed", "failed", "cancelled"].includes(String((e.data as { status?: string }).status)),
    });
    return () => {
      clearTimeout(refetchTimer);
      unsub();
    };
  }, [loaded, terminal, taskId, qc]);

  const events = React.useMemo(() => {
    const base = detail.data?.events ?? [];
    const seen = new Set(base.map((e) => e.id));
    return [...base, ...live.filter((e) => !seen.has(e.id))].sort((a, b) => a.id - b.id);
  }, [detail.data, live]);

  return { detail, events, draft, connection };
}

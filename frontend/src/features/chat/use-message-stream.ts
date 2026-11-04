"use client";

import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { keys } from "@/lib/queries";
import { subscribe } from "@/lib/sse";
import type { Analysis, Citation, Message } from "@/lib/types";

export type ToolEvent = {
  event: string;
  tool?: string;
  status?: string;
  url?: string;
  title?: string;
  domain?: string;
  error?: string | null;
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
  message?: string;
  label?: string;
  filename?: string;
  page?: number;
};

export type StreamState = {
  text: string;
  status: string | null;
  statusText: string | null;
  tools: ToolEvent[];
  sources: Citation[];
  analysis: Analysis | null;
  done: boolean;
  connection: string;
};

const initial: StreamState = { text: "", status: null, statusText: null, tools: [], sources: [], analysis: null, done: false, connection: "connecting" };

/** Follows a streaming assistant message; resumes automatically after network drops or page reloads. */
export function useMessageStream(message: Message | undefined, conversationId: string): StreamState {
  const qc = useQueryClient();
  const [state, setState] = React.useState<StreamState>(initial);
  const active = message?.role === "assistant" && message.status === "streaming" && !message.meta?.task_id;
  const id = message?.id;

  React.useEffect(() => {
    if (!active || !id) return;
    const unsub = subscribe(`/api/messages/${id}/stream`, {
      onStatus: (connection) => setState((s) => ({ ...s, connection })),
      onEvent: ({ event, data }) => {
        const d = data as Record<string, unknown>;
        setState((s) => {
          switch (event) {
            case "delta":
              return { ...s, text: s.text + String(d.text ?? "") };
            case "status":
              return { ...s, statusText: String(d.text ?? "") };
            case "tool":
              return { ...s, tools: [...s.tools, d as ToolEvent] };
            case "sources":
              return { ...s, sources: d.sources as Citation[] };
            case "analysis":
              return { ...s, analysis: d.analysis as Analysis };
            case "done":
              return { ...s, text: String(d.content ?? s.text), status: String(d.status), done: true };
            default:
              return s;
          }
        });
        if (event === "done" || event === "suggestions" || event === "end") {
          void qc.invalidateQueries({ queryKey: keys.messages(conversationId) });
        }
      },
      stopOn: (e) => e.event === "end",
    });
    return unsub;
  }, [active, id, conversationId, qc]);

  return state;
}

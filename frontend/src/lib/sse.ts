/**
 * Resumable Server-Sent Events over fetch (EventSource cannot send credentials headers reliably through proxies
 * and does not expose reconnection offsets). Tracks the last event id and reconnects with `Last-Event-ID`.
 */

export type SSEEvent = { event: string; data: unknown; id?: string };

export type SSEOptions = {
  onEvent: (e: SSEEvent) => void;
  onStatus?: (s: "connecting" | "open" | "reconnecting" | "closed") => void;
  stopOn?: (e: SSEEvent) => boolean;
  lastEventId?: string;
  maxRetries?: number;
};

export function subscribe(url: string, opts: SSEOptions): () => void {
  const controller = new AbortController();
  let lastId = opts.lastEventId;
  let retries = 0;
  let stopped = false;

  const run = async () => {
    while (!stopped) {
      opts.onStatus?.(retries ? "reconnecting" : "connecting");
      try {
        const res = await fetch(url, {
          credentials: "include",
          headers: lastId ? { "Last-Event-ID": lastId, Accept: "text/event-stream" } : { Accept: "text/event-stream" },
          signal: controller.signal,
          cache: "no-store",
        });
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
        opts.onStatus?.("open");
        retries = 0;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let idx;
          while ((idx = buf.indexOf("\n\n")) >= 0) {
            const raw = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const ev = parse(raw);
            if (!ev) continue;
            if (ev.id) lastId = ev.id;
            opts.onEvent(ev);
            if (opts.stopOn?.(ev)) {
              stopped = true;
              controller.abort();
              opts.onStatus?.("closed");
              return;
            }
          }
        }
        // server closed the stream normally
        stopped = true;
        opts.onStatus?.("closed");
        return;
      } catch (err) {
        if (stopped || controller.signal.aborted) return;
        retries += 1;
        if (retries > (opts.maxRetries ?? 8)) {
          opts.onStatus?.("closed");
          return;
        }
        await new Promise((r) => setTimeout(r, Math.min(500 * 2 ** retries, 8000)));
        void err;
      }
    }
  };
  void run();
  return () => {
    stopped = true;
    controller.abort();
  };
}

function parse(raw: string): SSEEvent | null {
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const i = line.indexOf(":");
    const field = i < 0 ? line : line.slice(0, i);
    const value = i < 0 ? "" : line.slice(i + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
    else if (field === "id") id = value;
  }
  if (!data.length) return null;
  const text = data.join("\n");
  let parsed: unknown = text;
  try {
    parsed = JSON.parse(text);
  } catch {
    /* plain text */
  }
  return { event, data: parsed, id };
}

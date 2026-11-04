import { afterEach, describe, expect, it, vi } from "vitest";

import { subscribe, type SSEEvent } from "@/lib/sse";

function streamOf(chunks: string[]) {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      chunks.forEach((x) => c.enqueue(enc.encode(x)));
      c.close();
    },
  });
}

afterEach(() => vi.restoreAllMocks());

describe("subscribe", () => {
  it("parses events split across chunks and stops on a terminal event", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(streamOf([
      "id: 1-0\nevent: delta\ndata: {\"text\":\"Hel",
      "lo\"}\n\n: keep-alive\n\nid: 2-0\nevent: delta\ndata: {\"text\":\" world\"}\n\n",
      "event: end\ndata: {}\n\n",
    ]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const events: SSEEvent[] = [];
    await new Promise<void>((resolve) => {
      subscribe("/api/x", { onEvent: (e) => events.push(e), stopOn: (e) => e.event === "end", onStatus: (s) => s === "closed" && resolve() });
    });
    expect(events.map((e) => e.event)).toEqual(["delta", "delta", "end"]);
    expect((events[0].data as { text: string }).text).toBe("Hello");
    expect(events[1].id).toBe("2-0");
  });

  it("reconnects with Last-Event-ID after a dropped connection", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(new ReadableStream({
        // first read delivers an event, the second read fails like a dropped connection
        pull: (() => {
          let n = 0;
          return (c: ReadableStreamDefaultController) => {
            if (n++ === 0) c.enqueue(new TextEncoder().encode("id: 7\nevent: task_event\ndata: {}\n\n"));
            else c.error(new Error("network drop"));
          };
        })(),
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(streamOf(["event: end\ndata: {}\n\n"]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await new Promise<void>((resolve) => {
      subscribe("/api/y", { onEvent: () => {}, stopOn: (e) => e.event === "end", onStatus: (s) => s === "closed" && resolve() });
    });
    vi.useRealTimers();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][1].headers["Last-Event-ID"]).toBe("7");
  });
});

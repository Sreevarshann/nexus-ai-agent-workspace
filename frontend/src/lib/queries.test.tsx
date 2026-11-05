import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useDocuments } from "@/lib/queries";

const doc = (status: string) => ({ id: "d1", filename: "a.pdf", status, chunk_count: 0, size: 1, mime: "application/pdf" });

afterEach(() => {
  focusManager.setFocused(undefined);
  vi.restoreAllMocks();
});

describe("useDocuments", () => {
  it("keeps polling an in-progress ingestion while the page is hidden, then stops once ready", async () => {
    const responses = [[doc("queued")], [doc("processing")], [doc("ready")]];
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(responses.shift() ?? [doc("ready")]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    focusManager.setFocused(false); // regression: a hidden tab used to freeze on "Processing"

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useDocuments(), { wrapper });

    await waitFor(() => expect(result.current.data?.[0].status).toBe("ready"), { timeout: 6000 });
    const calls = fetchMock.mock.calls.length;
    await new Promise((r) => setTimeout(r, 2000));
    expect(fetchMock.mock.calls.length).toBe(calls); // nothing in progress → polling stopped
  }, 10_000);
});

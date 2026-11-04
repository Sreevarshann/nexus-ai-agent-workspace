"use client";

import { Check, Globe2, Plus, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/overlay";

type Request = { kind: string; message?: string; web_queries?: string[]; max_sources?: number; agents?: string[]; preview?: string };

export function ApprovalDialog({ open, onOpenChange, request, onDecide }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  request: Request | undefined;
  onDecide: (d: { approved: boolean; comment: string; web_queries?: string[] }) => Promise<void>;
}) {
  const [queries, setQueries] = React.useState<string[]>(request?.web_queries ?? []);
  const [comment, setComment] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const key = JSON.stringify(request?.web_queries ?? []);
  const [prevKey, setPrevKey] = React.useState(key);
  if (key !== prevKey) {
    setPrevKey(key);
    setQueries(request?.web_queries ?? []);
  }

  const decide = async (approved: boolean) => {
    setBusy(true);
    try {
      await onDecide({ approved, comment, web_queries: request?.kind === "plan_approval" ? queries.filter((q) => q.trim()) : undefined });
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Approval required" description={request?.message ?? "The mission is paused at a human checkpoint."}>
        {request?.kind === "plan_approval" ? (
          <div className="space-y-3">
            <p className="text-[13px] text-ink-2">
              The agents want to search the live web with these queries and retrieve up to <b>{request.max_sources}</b> sources. Nothing has been fetched yet.
            </p>
            {queries.map((q, i) => (
              <div key={i} className="flex items-center gap-2">
                <Globe2 className="size-4 shrink-0 text-primary" />
                <Input value={q} onChange={(e) => setQueries((xs) => xs.map((x, j) => (j === i ? e.target.value : x)))} aria-label={`Query ${i + 1}`} />
                <Button variant="ghost" size="icon-sm" onClick={() => setQueries((xs) => xs.filter((_, j) => j !== i))} aria-label="Remove query"><X /></Button>
              </div>
            ))}
            {queries.length < 6 && (
              <Button variant="ghost" size="sm" onClick={() => setQueries((xs) => [...xs, ""])}><Plus /> Add query</Button>
            )}
          </div>
        ) : (
          request?.preview && <div className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl border border-line bg-surface-2 p-3 text-[12.5px] text-ink-2">{request.preview}</div>
        )}
        <Textarea className="mt-4" rows={2} placeholder="Optional note for the record" value={comment} onChange={(e) => setComment(e.target.value)} />
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="danger-ghost" disabled={busy} onClick={() => decide(false)}><X /> Reject</Button>
          <Button disabled={busy} onClick={() => decide(true)}><Check /> Approve and continue</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

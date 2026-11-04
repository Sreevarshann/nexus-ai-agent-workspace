"use client";

import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
      <AlertTriangle className="size-8 text-danger" />
      <h2 className="text-[18px] font-semibold text-ink">This view crashed</h2>
      <p className="max-w-md text-[13px] text-muted">{error.message}</p>
      <Button onClick={reset}>Reload view</Button>
    </div>
  );
}

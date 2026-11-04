import { Compass } from "lucide-react";
import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-bg px-6 text-center">
      <Compass className="size-8 text-primary" />
      <h1 className="text-[22px] font-semibold text-ink">Page not found</h1>
      <p className="text-[14px] text-muted">That page does not exist in this workspace.</p>
      <Link href="/workspace" className="mt-2 text-[14px] font-medium text-primary hover:underline">Back to the workspace</Link>
    </div>
  );
}

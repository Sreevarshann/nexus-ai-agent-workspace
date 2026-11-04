import type { Metadata } from "next";
import { Suspense } from "react";

import { KnowledgeLibrary } from "@/features/library/library";

export const metadata: Metadata = { title: "Knowledge Library" };

export default function LibraryPage() {
  return (
    <Suspense>
      <KnowledgeLibrary />
    </Suspense>
  );
}

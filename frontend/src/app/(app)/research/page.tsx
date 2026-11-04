import type { Metadata } from "next";

import { ResearchStudio } from "@/features/research/research-studio";

export const metadata: Metadata = { title: "Deep Research" };

export default function ResearchPage() {
  return <ResearchStudio />;
}

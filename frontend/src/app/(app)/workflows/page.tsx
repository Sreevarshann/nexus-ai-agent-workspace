import type { Metadata } from "next";

import { WorkflowList } from "@/features/workflows/workflow-list";

export const metadata: Metadata = { title: "Workflow Builder" };

export default function WorkflowsPage() {
  return <WorkflowList />;
}

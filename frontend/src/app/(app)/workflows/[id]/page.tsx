import { WorkflowEditor } from "@/features/workflows/workflow-editor";

export default async function WorkflowPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <WorkflowEditor id={id} />;
}

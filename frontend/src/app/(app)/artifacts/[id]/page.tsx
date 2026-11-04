import { ArtifactViewer } from "@/features/artifacts/artifact-studio";

export default async function ArtifactPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ArtifactViewer id={id} />;
}

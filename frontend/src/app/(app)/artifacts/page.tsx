import type { Metadata } from "next";

import { ArtifactList } from "@/features/artifacts/artifact-studio";

export const metadata: Metadata = { title: "Artifact Studio" };

export default function ArtifactsPage() {
  return <ArtifactList />;
}

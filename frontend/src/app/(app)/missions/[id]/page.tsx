import { MissionControl } from "@/features/missions/mission-control";

export default async function MissionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <MissionControl taskId={id} />;
}

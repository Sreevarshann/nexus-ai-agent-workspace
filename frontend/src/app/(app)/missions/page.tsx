import type { Metadata } from "next";

import { MissionList } from "@/features/missions/mission-list";

export const metadata: Metadata = { title: "Mission Control" };

export default function MissionsPage() {
  return <MissionList />;
}

import type { Metadata } from "next";

import { HistoryPage } from "@/features/settings/history";

export const metadata: Metadata = { title: "History" };

export default function Page() {
  return <HistoryPage />;
}

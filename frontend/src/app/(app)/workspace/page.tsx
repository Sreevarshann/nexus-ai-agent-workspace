import type { Metadata } from "next";

import { NewConversation } from "@/features/chat/workspace";

export const metadata: Metadata = { title: "Intelligence Workspace" };

export default function WorkspacePage() {
  return <NewConversation />;
}

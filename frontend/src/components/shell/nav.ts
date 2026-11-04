import {
  Activity,
  Archive,
  BookOpenText,
  Database,
  FlaskConical,
  History,
  type LucideIcon,
  MessagesSquare,
  Settings,
  Workflow,
} from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon; description: string; shortcut?: string };

export const NAV: NavItem[] = [
  { href: "/workspace", label: "Intelligence Workspace", icon: MessagesSquare, description: "Streaming chat with research, analysis and agent modes", shortcut: "1" },
  { href: "/missions", label: "Mission Control", icon: Activity, description: "Watch multi-agent missions execute", shortcut: "2" },
  { href: "/research", label: "Deep Research", icon: FlaskConical, description: "Plan and run research missions", shortcut: "3" },
  { href: "/library", label: "Knowledge Library", icon: BookOpenText, description: "Documents, passages and retrieval", shortcut: "4" },
  { href: "/data", label: "Data Lab", icon: Database, description: "Profile, query and chart datasets", shortcut: "5" },
  { href: "/artifacts", label: "Artifact Studio", icon: Archive, description: "Reports, analyses and exports", shortcut: "6" },
  { href: "/workflows", label: "Workflow Builder", icon: Workflow, description: "Compose and run typed pipelines", shortcut: "7" },
  { href: "/history", label: "History", icon: History, description: "Every conversation and task", shortcut: "8" },
];

export const SETTINGS_NAV: NavItem = { href: "/settings", label: "Settings", icon: Settings, description: "Models, connectors and tokens", shortcut: "9" };

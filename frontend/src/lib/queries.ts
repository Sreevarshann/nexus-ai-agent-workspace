"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  ArtifactSummary,
  Conversation,
  Dataset,
  DocumentItem,
  Health,
  Project,
  Task,
  User,
  Workflow,
} from "@/lib/types";

export const keys = {
  me: ["me"] as const,
  health: ["health"] as const,
  config: ["config"] as const,
  projects: ["projects"] as const,
  conversations: (q?: string) => ["conversations", q ?? ""] as const,
  messages: (id: string) => ["messages", id] as const,
  tasks: (kind?: string) => ["tasks", kind ?? "all"] as const,
  task: (id: string) => ["task", id] as const,
  documents: ["documents"] as const,
  datasets: ["datasets"] as const,
  artifacts: ["artifacts"] as const,
  artifact: (id: string) => ["artifact", id] as const,
  workflows: ["workflows"] as const,
  sources: ["sources"] as const,
  tools: ["tools"] as const,
  metrics: ["metrics"] as const,
};

export const useMe = () =>
  useQuery({ queryKey: keys.me, queryFn: () => api.get<User>("/auth/me"), retry: false, staleTime: 60_000 });

export const useHealth = () =>
  useQuery({ queryKey: keys.health, queryFn: () => api.get<Health>("/health"), refetchInterval: 20_000 });

export const useConfig = () =>
  useQuery({
    queryKey: keys.config,
    queryFn: () =>
      api.get<{
        llm: { provider: string; model: string; embed_model: string; temperature: number; num_ctx: number; timeout_s: number; external: boolean };
        search: { provider: string; url: string | null };
        limits: Record<string, number>;
      }>("/system/config"),
    staleTime: 60_000,
  });

export const useProjects = () => useQuery({ queryKey: keys.projects, queryFn: () => api.get<Project[]>("/projects") });

export const useConversations = (q?: string) =>
  useQuery({
    queryKey: keys.conversations(q),
    queryFn: () => api.get<Conversation[]>(`/conversations${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  });

export const useTasks = (kind?: string, refetch = true) =>
  useQuery({
    queryKey: keys.tasks(kind),
    queryFn: () => api.get<Task[]>(`/tasks${kind ? `?kind=${kind}` : ""}`),
    refetchInterval: (q) =>
      refetch && q.state.data?.some((t) => ["queued", "running"].includes(t.status)) ? 3000 : false,
  });

export const useDocuments = () =>
  useQuery({
    queryKey: keys.documents,
    queryFn: () => api.get<DocumentItem[]>("/documents"),
    refetchInterval: (q) => (q.state.data?.some((d) => ["queued", "processing"].includes(d.status)) ? 1500 : false),
  });

export const useDatasets = () => useQuery({ queryKey: keys.datasets, queryFn: () => api.get<Dataset[]>("/datasets") });

export const useArtifacts = () =>
  useQuery({ queryKey: keys.artifacts, queryFn: () => api.get<ArtifactSummary[]>("/artifacts") });

export const useWorkflows = () => useQuery({ queryKey: keys.workflows, queryFn: () => api.get<Workflow[]>("/workflows") });

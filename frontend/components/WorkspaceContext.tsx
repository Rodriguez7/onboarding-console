"use client";

import { createContext, useContext } from "react";
import type { WorkspaceDetail } from "@/lib/types";

type Ctx = { ws: WorkspaceDetail; refresh: () => Promise<void> };

export const WorkspaceContext = createContext<Ctx | null>(null);

/** The current workspace plus `refresh()`, which pages call after changes that affect progress. */
export function useWorkspace(): Ctx {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used inside a workspace page");
  return ctx;
}

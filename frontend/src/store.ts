import { create } from "zustand";

import { api } from "./api/client";
import type { HealthResponse, RequirementBehavior } from "./types/contracts";

type Role = "engineer" | "admin";

/** 현재 작업 중인 프로젝트 (satisfy·QA 가 참조). 실 BFF 는 프로젝트를 생성해야 satisfy 가 동작한다. */
export interface CurrentProject {
  id: string;
  name: string;
  categories: string[];
  requirements: RequirementBehavior[];
}

export type AuthorProvider = "solar" | "claude";

interface AppState {
  role: Role;
  setRole: (r: Role) => void;
  // T-90 — 저작 추출 provider. 기본 solar(무료). claude 는 옵션(유료)·명시적 opt-in. 세션 유지.
  authorProvider: AuthorProvider;
  setAuthorProvider: (p: AuthorProvider) => void;
  health: HealthResponse | null;
  healthError: boolean;
  fetchHealth: () => Promise<void>;
  project: CurrentProject | null;
  setProject: (p: CurrentProject | null) => void;
  setProjectRequirements: (rbs: RequirementBehavior[]) => void;
}

export const useApp = create<AppState>((set) => ({
  role: (localStorage.getItem("pkms_role") as Role) ?? "engineer",
  setRole: (r) => { localStorage.setItem("pkms_role", r); set({ role: r }); },
  authorProvider: (localStorage.getItem("pkms_author_provider") as AuthorProvider) ?? "solar",
  setAuthorProvider: (p) => { localStorage.setItem("pkms_author_provider", p); set({ authorProvider: p }); },
  health: null,
  healthError: false,
  fetchHealth: async () => {
    try {
      const h = await api.health();
      set({ health: h, healthError: false });
    } catch {
      set({ healthError: true });
    }
  },
  project: loadProject(),
  setProject: (p) => { saveProject(p); set({ project: p }); },
  setProjectRequirements: (rbs) =>
    set((s) => {
      if (!s.project) return {};
      const next = { ...s.project, requirements: rbs };
      saveProject(next);
      return { project: next };
    }),
}));

// currentProject 는 새로고침(full reload)에도 유지되도록 localStorage 에 보존한다.
function loadProject(): CurrentProject | null {
  try {
    const raw = localStorage.getItem("pkms_project");
    return raw ? (JSON.parse(raw) as CurrentProject) : null;
  } catch {
    return null;
  }
}
function saveProject(p: CurrentProject | null) {
  try {
    if (p) localStorage.setItem("pkms_project", JSON.stringify(p));
    else localStorage.removeItem("pkms_project");
  } catch { /* ignore */ }
}

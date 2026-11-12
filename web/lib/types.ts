export type Account = {
  id: string;
  nick: string;
  role: "farm" | "personal";
  enabled: boolean;
  status: "offline" | "connecting" | "ready" | "needs_login" | "rejected";
};

export type MetricDef = {
  key: string;
  label: string;
  unit: string;
  kind: "base" | "ratio";
  numerator: string | null;
  denominator: string | null;
  scale: number;
  description: string;
  sort: number;
};

export type CaptureFilter = {
  species?: string[];
  min_quality?: number;
  min_potency?: number;
  shiny?: boolean;
  min_iv_sum?: number;
  min_ivs?: Record<string, number>;
};

export type Goal = {
  id: string;
  name: string;
  kind: "metric" | "capture";
  account_id: string | null;
  hunt_slug: string | null;
  metric: string | null;
  filter: CaptureFilter;
  target: number;
  starts_at: string;
  deadline: string | null;
  status: "active" | "done" | "archived";
  created_at: string;
};

export type GoalProgress = {
  goal_id: string;
  current: number;
  target: number;
  pct: number | null;
  rate_per_hour: number | null;
  p_match: number | null;
  eta: string | null;
  on_track: boolean | null;
  chance_by_deadline: number | null;
};

export type Snapshot = {
  taken_at: string;
  current: number;
  rate_per_hour: number | null;
  eta: string | null;
  chance_by_deadline: number | null;
};

export const STATUS_LABEL: Record<Account["status"], string> = {
  offline: "Offline",
  connecting: "Conectando",
  ready: "Pronta",
  needs_login: "Precisa de login",
  rejected: "Rejeitada",
};

export const IV_STATS = ["hp", "atk", "def", "spa", "spd", "spe"] as const;

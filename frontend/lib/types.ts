export type Step = { key: string; label: string; complete: boolean; detail: string };

export type Workspace = {
  id: string;
  name: string;
  slug: string;
  customer_contact_email: string;
  specialist_name: string;
  target_go_live: string | null;
  status: "onboarding" | "live";
  went_live_at: string | null;
  created_at: string;
};

export type WorkspaceDetail = Workspace & { steps: Step[]; blockers: string[] };

export type PlatformField = {
  name: string;
  label: string;
  type: string;
  required: boolean;
  description: string;
  options: string[];
};

export type ImportJob = {
  id: string;
  workspace_id: string;
  filename: string;
  headers: string[];
  mapping: Record<string, string | null>;
  status: "uploaded" | "validated" | "committed";
  row_count: number;
  valid_count: number;
  invalid_count: number;
  committed_count: number;
  created_at: string;
};

export type ImportJobCreated = ImportJob & {
  suggested_mapping: Record<string, { field: string | null; confidence: number }>;
  preview: Record<string, string>[];
};

export type FieldError = { field: string; message: string };

export type ImportRow = {
  id: string;
  row_number: number;
  raw: Record<string, string>;
  overrides: Record<string, string>;
  normalized: Record<string, unknown>;
  errors: FieldError[];
  is_valid: boolean;
};

export type Credential = {
  id: string;
  name: string;
  environment: "sandbox" | "production";
  key_prefix: string;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export type Webhook = {
  id: string;
  url: string;
  description: string;
  events: string[];
  secret: string;
  active: boolean;
  created_at: string;
};

export type Delivery = {
  id: string;
  endpoint_id: string;
  event: string;
  payload: Record<string, unknown>;
  attempt: number;
  success: boolean;
  status_code: number | null;
  error: string | null;
  response_excerpt: string | null;
  duration_ms: number;
  created_at: string;
};

export type Check = { key: string; name: string; status: "passed" | "warning" | "failed"; detail: string };
export type TestRun = { id: string; passed: boolean; checks: Check[]; created_at: string };

export type UATItem = {
  id: string;
  position: number;
  category: string;
  title: string;
  done: boolean;
  notes: string;
  completed_by: string | null;
  completed_at: string | null;
};

export type Monitoring = {
  window_hours: number;
  health: "healthy" | "degraded" | "down" | "no_traffic";
  workspace_status: string;
  went_live_at: string | null;
  records_total: number;
  api: { requests: number; errors: number; rejected: number; error_rate: number; p95_latency_ms: number | null };
  webhooks: { deliveries: number; failed: number; failure_rate: number; p95_latency_ms: number | null };
  last_activity_at: string | null;
  series: { hour: string; requests: number; errors: number; deliveries: number; failed_deliveries: number }[];
  recent_errors: { kind: "api" | "webhook"; at: string; status_code: number | null; message: string }[];
};

export const WEBHOOK_EVENTS = ["records.imported", "record.upserted", "integration.test", "workspace.live"] as const;

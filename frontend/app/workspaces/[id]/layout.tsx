"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { ReactNode } from "react";
import { Badge, ErrorBanner, useLoad } from "@/components/ui";
import { WorkspaceContext } from "@/components/WorkspaceContext";
import { api } from "@/lib/api";
import type { WorkspaceDetail } from "@/lib/types";

// Nav entries; `step` ties an entry to the backend's progress step for its check mark.
const NAV = [
  { href: "", label: "Overview" },
  { href: "/import", label: "Import & mapping", step: "mapping" },
  { href: "/integrations", label: "Credentials & webhooks", step: "integrations" },
  { href: "/tests", label: "Validation & tests", step: "tests" },
  { href: "/issues", label: "Failed records & errors" },
  { href: "/uat", label: "UAT checklist", step: "uat" },
  { href: "/handover", label: "Handover document" },
  { href: "/monitor", label: "Monitoring", step: "live" },
];

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const pathname = usePathname();
  const { data: ws, error, reload } = useLoad(() => api<WorkspaceDetail>(`/workspaces/${id}`), [id]);

  if (error) return <ErrorBanner error={error} />;
  if (!ws) return <p className="muted">Loading workspace…</p>;

  const base = `/workspaces/${id}`;
  const done = (key?: string) => ws.steps.find((s) => s.key === key)?.complete;

  return (
    <WorkspaceContext.Provider value={{ ws, refresh: reload }}>
      <div className="page-head">
        <div>
          <div className="muted">
            <Link href="/">Workspaces</Link> / {ws.slug}
          </div>
          <h1>{ws.name}</h1>
          <div className="subtle">
            {ws.specialist_name} · {ws.customer_contact_email}
          </div>
        </div>
        {ws.status === "live" ? <Badge tone="good">Live</Badge> : <Badge tone="info">Onboarding</Badge>}
      </div>
      <div className="ws-shell">
        <nav className="ws-nav" aria-label="Onboarding steps">
          {NAV.map((n, i) => {
            const href = base + n.href;
            const active = n.href ? pathname.startsWith(href) : pathname === base;
            const complete = n.step ? done(n.step) : false;
            return (
              <Link key={n.href} href={href} className={active ? "active" : ""} aria-current={active ? "page" : undefined}>
                <span className={`step-dot ${complete ? "done" : ""}`} aria-label={complete ? "complete" : undefined}>
                  {complete ? "✓" : i + 1}
                </span>
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div>{children}</div>
      </div>
    </WorkspaceContext.Provider>
  );
}

"use client";

import Link from "next/link";
import { Badge, Card, ErrorBanner, fmtDate, useAction } from "@/components/ui";
import { useWorkspace } from "@/components/WorkspaceContext";
import { api } from "@/lib/api";

const STEP_LINKS: Record<string, string> = {
  import: "/import",
  mapping: "/import",
  integrations: "/integrations",
  tests: "/tests",
  uat: "/uat",
  live: "/monitor",
};

export default function Overview() {
  const { ws, refresh } = useWorkspace();
  const goLive = useAction();
  const completed = ws.steps.filter((s) => s.complete).length;

  async function launch() {
    await goLive.run(() => api(`/workspaces/${ws.id}/go-live`, { method: "POST" }));
    await refresh();
  }

  return (
    <>
      <Card title="Onboarding progress" actions={<span className="muted">{completed} of {ws.steps.length} steps</span>}>
        <div className="progress" style={{ marginBottom: 16 }}>
          <div style={{ width: `${(completed / ws.steps.length) * 100}%` }} />
        </div>
        <div className="table-wrap">
          <table>
            <tbody>
              {ws.steps.map((s) => (
                <tr key={s.key}>
                  <td style={{ width: 110 }}>
                    {s.complete ? <Badge tone="good">Done</Badge> : <Badge tone="neutral">To do</Badge>}
                  </td>
                  <td>
                    {STEP_LINKS[s.key] ? <Link href={`/workspaces/${ws.id}${STEP_LINKS[s.key]}`}>{s.label}</Link> : s.label}
                  </td>
                  <td className="subtle">{s.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Go-live">
        <ErrorBanner error={goLive.error} />
        {ws.status === "live" ? (
          <div className="banner banner-good">
            Live since {fmtDate(ws.went_live_at)}. Track the integration on the{" "}
            <Link href={`/workspaces/${ws.id}/monitor`}>Monitoring</Link> page.
          </div>
        ) : ws.blockers.length ? (
          <div className="banner banner-warning">
            <strong>Not ready yet</strong>
            <ul>
              {ws.blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="banner banner-good">All gates passed — ready to launch.</div>
        )}
        <div className="row">
          <button className="primary" onClick={launch} disabled={ws.status === "live" || ws.blockers.length > 0 || goLive.busy}>
            {goLive.busy ? "Launching…" : "Go live"}
          </button>
          <span className="muted">Target date: {fmtDate(ws.target_go_live, false)}</span>
        </div>
      </Card>
    </>
  );
}

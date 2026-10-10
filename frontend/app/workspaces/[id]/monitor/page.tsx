"use client";

import { useEffect } from "react";
import { HourlyChart } from "@/components/HourlyChart";
import { Badge, Card, Empty, ErrorBanner, Stat, fmtDate, useLoad } from "@/components/ui";
import { useWorkspace } from "@/components/WorkspaceContext";
import { api } from "@/lib/api";
import type { Monitoring } from "@/lib/types";

const HEALTH = {
  healthy: { tone: "good", label: "Healthy" },
  degraded: { tone: "warning", label: "Degraded" },
  down: { tone: "critical", label: "Down" },
  no_traffic: { tone: "neutral", label: "No traffic" },
} as const;

const pct = (n: number) => `${(n * 100).toFixed(n && n < 0.01 ? 2 : 1)}%`;
const hourLabel = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

export default function MonitorPage() {
  const { ws } = useWorkspace();
  const m = useLoad(() => api<Monitoring>(`/workspaces/${ws.id}/monitoring?hours=24`), [ws.id]);

  useEffect(() => {
    const t = setInterval(() => void m.reload(), 30_000);
    return () => clearInterval(t);
  }, [m.reload]); // eslint-disable-line react-hooks/exhaustive-deps

  if (m.error) return <ErrorBanner error={m.error} />;
  if (!m.data) return <p className="muted">Loading…</p>;
  const d = m.data;
  const h = HEALTH[d.health];

  return (
    <>
      {ws.status !== "live" && (
        <div className="banner banner-info">
          This workspace hasn&apos;t gone live yet — metrics below include test traffic.
        </div>
      )}
      <Card
        title="Integration health · last 24 hours"
        actions={
          <>
            <Badge tone={h.tone}>{h.label}</Badge>
            <button className="small" onClick={() => m.reload()}>
              Refresh
            </button>
          </>
        }
      >
        <div className="stats">
          <Stat label="API requests" value={d.api.requests} hint={`${d.api.rejected} rejected payloads`} />
          <Stat label="API error rate" value={pct(d.api.error_rate)} hint={`${d.api.errors} auth/server errors`} />
          <Stat label="API p95 latency" value={d.api.p95_latency_ms != null ? `${d.api.p95_latency_ms} ms` : "—"} />
          <Stat label="Webhook deliveries" value={d.webhooks.deliveries} hint={`${d.webhooks.failed} failed`} />
          <Stat label="Webhook failure rate" value={pct(d.webhooks.failure_rate)} />
          <Stat label="Customer records" value={d.records_total} hint={`Last activity ${fmtDate(d.last_activity_at)}`} />
        </div>
        <div className="grid-2">
          <div>
            <h3>API requests / hour</h3>
            <HourlyChart
              okLabel="Successful"
              badLabel="Errors & rejections"
              buckets={d.series.map((s) => ({ label: hourLabel(s.hour), ok: s.requests - s.errors, bad: s.errors }))}
            />
          </div>
          <div>
            <h3>Webhook deliveries / hour</h3>
            <HourlyChart
              okLabel="Delivered"
              badLabel="Failed"
              buckets={d.series.map((s) => ({
                label: hourLabel(s.hour),
                ok: s.deliveries - s.failed_deliveries,
                bad: s.failed_deliveries,
              }))}
            />
          </div>
        </div>
        <details style={{ marginTop: 12 }}>
          <summary className="muted">Show hourly data as a table</summary>
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table>
              <thead>
                <tr>
                  <th>Hour</th>
                  <th className="num">Requests</th>
                  <th className="num">Errors</th>
                  <th className="num">Deliveries</th>
                  <th className="num">Failed</th>
                </tr>
              </thead>
              <tbody>
                {d.series
                  .filter((s) => s.requests || s.deliveries)
                  .map((s) => (
                    <tr key={s.hour}>
                      <td>{fmtDate(s.hour)}</td>
                      <td className="num">{s.requests}</td>
                      <td className="num">{s.errors}</td>
                      <td className="num">{s.deliveries}</td>
                      <td className="num">{s.failed_deliveries}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </details>
      </Card>

      <Card title="Recent errors">
        {d.recent_errors.length === 0 ? (
          <Empty>No errors in this window.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {d.recent_errors.map((e, i) => (
                  <tr key={i}>
                    <td>{fmtDate(e.at)}</td>
                    <td>{e.kind === "api" ? "Customer API" : "Webhook"}</td>
                    <td>
                      <Badge tone={e.status_code === 422 ? "warning" : "critical"}>{e.status_code ?? "no response"}</Badge>
                    </td>
                    <td className="subtle">{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

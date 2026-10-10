"use client";

import { Badge, Card, Empty, ErrorBanner, fmtDate, useAction, useLoad } from "@/components/ui";
import { useWorkspace } from "@/components/WorkspaceContext";
import { api } from "@/lib/api";
import type { Check, TestRun } from "@/lib/types";

const TONE = { passed: "good", warning: "warning", failed: "critical" } as const;

export default function TestsPage() {
  const { ws, refresh } = useWorkspace();
  const runs = useLoad(() => api<TestRun[]>(`/workspaces/${ws.id}/test-runs`), [ws.id]);
  const run = useAction();

  async function start() {
    await run.run(() => api<TestRun>(`/workspaces/${ws.id}/test-runs`, { method: "POST" }));
    await Promise.all([runs.reload(), refresh()]);
  }

  const [latest, ...history] = runs.data ?? [];
  const counts = (checks: Check[]) =>
    (["passed", "warning", "failed"] as const).map((s) => [s, checks.filter((c) => c.status === s).length] as const);

  return (
    <>
      <Card
        title="Validation & integration tests"
        actions={
          <button className="primary" onClick={start} disabled={run.busy}>
            {run.busy ? "Running…" : "Run tests"}
          </button>
        }
      >
        <p className="subtle" style={{ marginTop: 0 }}>
          Checks the imported data, mapping, credentials and sends a signed <code>integration.test</code> event to every
          active webhook. Go-live requires a run with no failures; warnings are allowed.
        </p>
        <ErrorBanner error={run.error || runs.error} />
        {runs.data && !latest && <Empty>No test runs yet.</Empty>}
        {latest && (
          <>
            <div className={`banner ${latest.passed ? "banner-good" : "banner-critical"}`} data-testid="test-result">
              <strong>{latest.passed ? "Passed" : "Failed"}</strong> · {fmtDate(latest.created_at)} ·{" "}
              {counts(latest.checks)
                .map(([s, n]) => `${n} ${s}`)
                .join(", ")}
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 110 }}>Result</th>
                    <th>Check</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {latest.checks.map((c) => (
                    <tr key={c.key}>
                      <td>
                        <Badge tone={TONE[c.status]}>{c.status}</Badge>
                      </td>
                      <td>{c.name}</td>
                      <td className="subtle">{c.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>

      {history.length > 0 && (
        <Card title="Previous runs">
          <div className="table-wrap">
            <table>
              <tbody>
                {history.map((r) => (
                  <tr key={r.id}>
                    <td style={{ width: 110 }}>
                      <Badge tone={r.passed ? "good" : "critical"}>{r.passed ? "passed" : "failed"}</Badge>
                    </td>
                    <td>{fmtDate(r.created_at)}</td>
                    <td className="subtle">
                      {r.checks
                        .filter((c) => c.status === "failed")
                        .map((c) => c.name)
                        .join(", ") || "No failures"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}

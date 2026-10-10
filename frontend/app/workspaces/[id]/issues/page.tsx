"use client";

import { useState } from "react";
import { Badge, Card, Empty, ErrorBanner, fmtDate, useAction, useLoad } from "@/components/ui";
import { useWorkspace } from "@/components/WorkspaceContext";
import { api, json } from "@/lib/api";
import type { Delivery, ImportJob, ImportRow, Webhook } from "@/lib/types";

function RowEditor({ row, job, onSaved }: { row: ImportRow; job: ImportJob; onSaved: () => Promise<void> }) {
  const { ws } = useWorkspace();
  const badFields = [...new Set(row.errors.map((e) => e.field))];
  const sourceFor = (field: string) => Object.entries(job.mapping).find(([, t]) => t === field)?.[0];
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      badFields.map((f) => {
        const src = sourceFor(f);
        return [f, row.overrides[f] ?? (src ? row.raw[src] : "") ?? ""];
      }),
    ),
  );
  const save = useAction();

  async function submit() {
    const ok = await save.run(() =>
      api(`/workspaces/${ws.id}/imports/${job.id}/rows/${row.id}`, json({ values }, "PATCH")),
    );
    if (ok) await onSaved();
  }

  return (
    <tr>
      <td className="num">{row.row_number}</td>
      <td>
        <ul style={{ margin: 0, paddingLeft: 16 }}>
          {row.errors.map((e, i) => (
            <li key={i} className="err-text">
              {e.message}
            </li>
          ))}
        </ul>
      </td>
      <td>
        {job.status === "committed" ? (
          <span className="muted">Skipped at commit</span>
        ) : (
          <div className="stack" style={{ gap: 6 }}>
            {badFields.map((f) => (
              <label key={f} style={{ fontWeight: 400 }}>
                <code>{f}</code>
                <input
                  aria-label={`Row ${row.row_number} ${f}`}
                  value={values[f]}
                  onChange={(e) => setValues({ ...values, [f]: e.target.value })}
                />
              </label>
            ))}
            <ErrorBanner error={save.error} />
            <div>
              <button className="small primary" onClick={submit} disabled={save.busy}>
                Save & revalidate
              </button>
            </div>
          </div>
        )}
      </td>
    </tr>
  );
}

export default function IssuesPage() {
  const { ws, refresh } = useWorkspace();
  const jobs = useLoad(() => api<ImportJob[]>(`/workspaces/${ws.id}/imports`), [ws.id]);
  const job = jobs.data?.[0];
  const rows = useLoad(
    () =>
      job && job.status !== "uploaded"
        ? api<ImportRow[]>(`/workspaces/${ws.id}/imports/${job.id}/rows?status=invalid`)
        : Promise.resolve([] as ImportRow[]),
    [ws.id, job?.id, job?.status],
  );
  const failures = useLoad(() => api<Delivery[]>(`/workspaces/${ws.id}/webhook-deliveries?failed=true`), [ws.id]);
  const hooks = useLoad(() => api<Webhook[]>(`/workspaces/${ws.id}/webhooks`), [ws.id]);
  const retry = useAction();

  async function afterFix() {
    await Promise.all([jobs.reload(), rows.reload(), refresh()]);
  }

  async function retryDelivery(d: Delivery) {
    await retry.run(() => api(`/workspaces/${ws.id}/webhook-deliveries/${d.id}/retry`, { method: "POST" }));
    await failures.reload();
  }

  const urlFor = (id: string) => hooks.data?.find((h) => h.id === id)?.url ?? "(deleted endpoint)";

  return (
    <>
      <Card
        title="Failed records"
        actions={job && <span className="muted">{job.filename}</span>}
      >
        <ErrorBanner error={jobs.error || rows.error} />
        {!job && <Empty>No import yet.</Empty>}
        {job?.status === "uploaded" && <Empty>Apply a field mapping to validate records.</Empty>}
        {job && job.status !== "uploaded" && rows.data?.length === 0 && (
          <div className="banner banner-good">All {job.row_count} records passed validation.</div>
        )}
        {job && !!rows.data?.length && (
          <>
            <p className="subtle" style={{ marginTop: 0 }}>
              {rows.data.length} record(s) failed validation. Correct the values below — fixes are stored as overrides on
              top of the original CSV values.
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th className="num" style={{ width: 60 }}>Row</th>
                    <th>Problems</th>
                    <th style={{ width: 320 }}>Fix</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.data.map((r) => (
                    <RowEditor key={`${r.id}-${r.errors.length}`} row={r} job={job} onSaved={afterFix} />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>

      <Card title="Webhook errors">
        <ErrorBanner error={retry.error || failures.error} />
        {failures.data?.length === 0 && <Empty>No failed webhook deliveries.</Empty>}
        {!!failures.data?.length && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Endpoint</th>
                  <th>Event</th>
                  <th>Error</th>
                  <th className="num">Attempt</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {failures.data.map((d) => (
                  <tr key={d.id}>
                    <td>{fmtDate(d.created_at)}</td>
                    <td>
                      <code>{urlFor(d.endpoint_id)}</code>
                    </td>
                    <td>
                      <code>{d.event}</code>
                    </td>
                    <td>
                      <Badge tone="critical">{d.status_code ?? "no response"}</Badge>{" "}
                      <span className="subtle">{d.error}</span>
                      {d.response_excerpt && (
                        <details>
                          <summary className="muted">Response body</summary>
                          <pre className="secret" style={{ whiteSpace: "pre-wrap" }}>{d.response_excerpt}</pre>
                        </details>
                      )}
                    </td>
                    <td className="num">{d.attempt}</td>
                    <td className="num">
                      <button className="small" onClick={() => retryDelivery(d)} disabled={retry.busy}>
                        Retry
                      </button>
                    </td>
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

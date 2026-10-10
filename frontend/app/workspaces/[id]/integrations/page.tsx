"use client";

import { FormEvent, useState } from "react";
import { Badge, Card, Empty, ErrorBanner, fmtDate, useAction, useLoad } from "@/components/ui";
import { useWorkspace } from "@/components/WorkspaceContext";
import { API_URL, api, json } from "@/lib/api";
import { WEBHOOK_EVENTS, type Credential, type Delivery, type Webhook } from "@/lib/types";

export default function IntegrationsPage() {
  const { ws, refresh } = useWorkspace();
  const creds = useLoad(() => api<Credential[]>(`/workspaces/${ws.id}/credentials`), [ws.id]);
  const hooks = useLoad(() => api<Webhook[]>(`/workspaces/${ws.id}/webhooks`), [ws.id]);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [lastTest, setLastTest] = useState<Record<string, Delivery>>({});
  const [events, setEvents] = useState<string[]>([...WEBHOOK_EVENTS]);
  const action = useAction();

  async function createKey(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const created = await action.run(() =>
      api<Credential & { api_key: string }>(
        `/workspaces/${ws.id}/credentials`,
        json({ name: f.get("name"), environment: f.get("environment") }),
      ),
    );
    if (created) {
      setNewKey(created.api_key);
      form.reset();
      await Promise.all([creds.reload(), refresh()]);
    }
  }

  async function revoke(id: string) {
    if (!confirm("Revoke this key? Requests using it will start failing immediately.")) return;
    await action.run(() => api(`/workspaces/${ws.id}/credentials/${id}`, { method: "DELETE" }));
    await Promise.all([creds.reload(), refresh()]);
  }

  async function createHook(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const ok = await action.run(() =>
      api(`/workspaces/${ws.id}/webhooks`, json({ url: f.get("url"), description: f.get("description"), events })),
    );
    if (ok) {
      form.reset();
      await Promise.all([hooks.reload(), refresh()]);
    }
  }

  async function toggle(h: Webhook) {
    await action.run(() => api(`/workspaces/${ws.id}/webhooks/${h.id}`, json({ active: !h.active }, "PATCH")));
    await Promise.all([hooks.reload(), refresh()]);
  }

  async function remove(h: Webhook) {
    if (!confirm(`Delete webhook ${h.url}?`)) return;
    await action.run(() => api(`/workspaces/${ws.id}/webhooks/${h.id}`, { method: "DELETE" }));
    await Promise.all([hooks.reload(), refresh()]);
  }

  async function test(h: Webhook) {
    const d = await action.run(() => api<Delivery>(`/workspaces/${ws.id}/webhooks/${h.id}/test`, { method: "POST" }));
    if (d) setLastTest({ ...lastTest, [h.id]: d });
  }

  return (
    <>
      <ErrorBanner error={action.error || creds.error || hooks.error} />

      <Card title="API credentials">
        {newKey && (
          <div className="banner banner-warning">
            <strong>Copy this key now — it won&apos;t be shown again.</strong>
            <div className="secret" data-testid="new-api-key" style={{ marginTop: 6 }}>
              {newKey}
            </div>
            <button className="small" style={{ marginTop: 6 }} onClick={() => navigator.clipboard?.writeText(newKey)}>
              Copy
            </button>
          </div>
        )}
        <form onSubmit={createKey} className="form-grid" style={{ marginBottom: 14 }}>
          <label>
            Key name
            <input name="name" required minLength={2} placeholder="Production CRM sync" />
          </label>
          <label>
            Environment
            <select name="environment" defaultValue="sandbox">
              <option value="sandbox">Sandbox</option>
              <option value="production">Production</option>
            </select>
          </label>
          <div>
            <button className="primary" disabled={action.busy}>
              Generate key
            </button>
          </div>
        </form>
        {creds.data?.length === 0 && <Empty>No API keys yet.</Empty>}
        {!!creds.data?.length && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Environment</th>
                  <th>Key</th>
                  <th>Last used</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {creds.data.map((c) => (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td>{c.environment === "production" ? <Badge tone="info">production</Badge> : "sandbox"}</td>
                    <td>
                      <code>{c.key_prefix}…</code>
                    </td>
                    <td>{fmtDate(c.last_used_at)}</td>
                    <td>{c.revoked_at ? <Badge tone="neutral">revoked</Badge> : <Badge tone="good">active</Badge>}</td>
                    <td className="num">
                      {!c.revoked_at && (
                        <button className="small danger" onClick={() => revoke(c.id)}>
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted">
          Customers call <code>POST {API_URL}/api/v1/records</code> with <code>Authorization: Bearer &lt;key&gt;</code>.
        </p>
      </Card>

      <Card title="Webhook endpoints">
        <form onSubmit={createHook} className="stack" style={{ marginBottom: 14 }}>
          <div className="form-grid">
            <label>
              Endpoint URL
              <input name="url" type="url" required placeholder="https://customer.example.com/webhooks" />
            </label>
            <label>
              Description
              <input name="description" placeholder="Customer CRM listener" />
            </label>
          </div>
          <div className="row">
            {WEBHOOK_EVENTS.map((ev) => (
              <label key={ev} className="row" style={{ flexDirection: "row", fontWeight: 400 }}>
                <input
                  type="checkbox"
                  checked={events.includes(ev)}
                  onChange={(e) => setEvents(e.target.checked ? [...events, ev] : events.filter((x) => x !== ev))}
                />
                <code>{ev}</code>
              </label>
            ))}
          </div>
          <div className="row">
            <button className="primary" disabled={action.busy || events.length === 0}>
              Add endpoint
            </button>
            <span className="muted">
              No receiver yet? Use <code>{API_URL}/sink/ok</code> (accepts) or <code>{API_URL}/sink/fail</code> (returns 500).
            </span>
          </div>
        </form>
        {hooks.data?.length === 0 && <Empty>No webhook endpoints yet.</Empty>}
        <div className="stack">
          {hooks.data?.map((h) => {
            const t = lastTest[h.id];
            return (
              <div key={h.id} className="card" style={{ margin: 0 }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div>
                    <code>{h.url}</code> {h.active ? <Badge tone="good">active</Badge> : <Badge tone="neutral">paused</Badge>}
                    {h.description && <div className="muted">{h.description}</div>}
                  </div>
                  <div className="row">
                    <button className="small" onClick={() => test(h)} disabled={action.busy}>
                      Send test event
                    </button>
                    <button className="small" onClick={() => toggle(h)}>
                      {h.active ? "Pause" : "Resume"}
                    </button>
                    <button className="small danger" onClick={() => remove(h)}>
                      Delete
                    </button>
                  </div>
                </div>
                <div className="muted" style={{ marginTop: 6 }}>
                  Events: {h.events.join(", ")}
                </div>
                <details style={{ marginTop: 6 }}>
                  <summary className="muted">Signing secret</summary>
                  <div className="secret">{h.secret}</div>
                </details>
                {t && (
                  <div className={`banner ${t.success ? "banner-good" : "banner-critical"}`} style={{ marginTop: 8, marginBottom: 0 }}>
                    {t.success
                      ? `Test delivered — HTTP ${t.status_code} in ${t.duration_ms.toFixed(0)} ms`
                      : `Test failed — ${t.error}`}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent } from "react";
import { Badge, Card, Empty, ErrorBanner, fmtDate, useAction, useLoad } from "@/components/ui";
import { api, json } from "@/lib/api";
import type { Workspace, WorkspaceDetail } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  const { data: workspaces, error } = useLoad(() => api<Workspace[]>("/workspaces"), []);
  const create = useAction();

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const ws = await create.run(() =>
      api<WorkspaceDetail>(
        "/workspaces",
        json({
          name: f.get("name"),
          customer_contact_email: f.get("email"),
          specialist_name: f.get("specialist"),
          target_go_live: f.get("target") || null,
        }),
      ),
    );
    if (ws) router.push(`/workspaces/${ws.id}`);
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Customer workspaces</h1>
          <p className="subtle">Each workspace tracks one customer from configuration to go-live.</p>
        </div>
      </div>

      <Card title="Create a workspace">
        <ErrorBanner error={create.error} />
        <form onSubmit={onSubmit} className="form-grid">
          <label>
            Customer name
            <input name="name" required minLength={2} placeholder="Acme Corp" />
          </label>
          <label>
            Customer contact email
            <input name="email" type="email" required placeholder="ops@acme.com" />
          </label>
          <label>
            Implementation specialist
            <input name="specialist" required minLength={2} placeholder="Your name" />
          </label>
          <label>
            Target go-live
            <input name="target" type="date" />
          </label>
          <div>
            <button className="primary" disabled={create.busy}>
              {create.busy ? "Creating…" : "Create workspace"}
            </button>
          </div>
        </form>
      </Card>

      <Card title="All workspaces">
        <ErrorBanner error={error} />
        {workspaces && workspaces.length === 0 && <Empty>No workspaces yet — create one above.</Empty>}
        {workspaces && workspaces.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Status</th>
                  <th>Specialist</th>
                  <th>Target go-live</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {workspaces.map((w) => (
                  <tr key={w.id}>
                    <td>
                      <Link href={`/workspaces/${w.id}`}>{w.name}</Link>
                    </td>
                    <td>
                      {w.status === "live" ? <Badge tone="good">Live</Badge> : <Badge tone="info">Onboarding</Badge>}
                    </td>
                    <td>{w.specialist_name}</td>
                    <td>{fmtDate(w.target_go_live, false)}</td>
                    <td>{fmtDate(w.created_at)}</td>
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

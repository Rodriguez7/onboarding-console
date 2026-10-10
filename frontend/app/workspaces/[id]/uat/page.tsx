"use client";

import { FormEvent, useState } from "react";
import { Card, ErrorBanner, fmtDate, useAction, useLoad } from "@/components/ui";
import { useWorkspace } from "@/components/WorkspaceContext";
import { api, json } from "@/lib/api";
import type { UATItem } from "@/lib/types";

export default function UATPage() {
  const { ws, refresh } = useWorkspace();
  const items = useLoad(() => api<UATItem[]>(`/workspaces/${ws.id}/uat`), [ws.id]);
  const [signer, setSigner] = useState("");
  const action = useAction();

  async function update(item: UATItem, body: Partial<UATItem>) {
    const ok = await action.run(() => api(`/workspaces/${ws.id}/uat/${item.id}`, json(body, "PATCH")));
    if (ok) await Promise.all([items.reload(), refresh()]);
  }

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const ok = await action.run(() =>
      api(`/workspaces/${ws.id}/uat`, json({ category: f.get("category"), title: f.get("title") })),
    );
    if (ok) {
      form.reset();
      await Promise.all([items.reload(), refresh()]);
    }
  }

  const list = items.data ?? [];
  const done = list.filter((i) => i.done).length;
  const categories = [...new Set(list.map((i) => i.category))];

  return (
    <>
      <Card title="UAT checklist" actions={<span className="muted">{done} of {list.length} complete</span>}>
        <div className="progress" style={{ marginBottom: 14 }}>
          <div style={{ width: list.length ? `${(done / list.length) * 100}%` : 0 }} />
        </div>
        <label style={{ maxWidth: 320, marginBottom: 14 }}>
          Signing off as
          <input value={signer} onChange={(e) => setSigner(e.target.value)} placeholder="Customer stakeholder name" />
        </label>
        <ErrorBanner error={action.error || items.error} />
        {categories.map((cat) => (
          <div key={cat}>
            <h3>{cat}</h3>
            <div className="table-wrap">
              <table>
                <tbody>
                  {list
                    .filter((i) => i.category === cat)
                    .map((i) => (
                      <tr key={i.id}>
                        <td style={{ width: 36 }}>
                          <input
                            type="checkbox"
                            aria-label={i.title}
                            checked={i.done}
                            disabled={action.busy || (!i.done && !signer.trim())}
                            title={!i.done && !signer.trim() ? "Enter who is signing off first" : undefined}
                            onChange={(e) => update(i, { done: e.target.checked, completed_by: signer })}
                          />
                        </td>
                        <td>
                          <div>{i.title}</div>
                          {i.done && (
                            <div className="muted">
                              Signed off by {i.completed_by} · {fmtDate(i.completed_at)}
                            </div>
                          )}
                        </td>
                        <td style={{ width: 260 }}>
                          <input
                            aria-label={`Notes for ${i.title}`}
                            defaultValue={i.notes}
                            placeholder="Notes"
                            style={{ width: "100%" }}
                            onBlur={(e) => e.target.value !== i.notes && update(i, { notes: e.target.value })}
                          />
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </Card>

      <Card title="Add a custom check">
        <form onSubmit={add} className="form-grid">
          <label>
            Category
            <input name="category" required list="uat-categories" placeholder="Integration" />
            <datalist id="uat-categories">
              {categories.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </label>
          <label style={{ gridColumn: "span 2" }}>
            Item
            <input name="title" required minLength={3} placeholder="Customer confirms nightly sync window" />
          </label>
          <div>
            <button className="primary" disabled={action.busy}>
              Add item
            </button>
          </div>
        </form>
      </Card>
    </>
  );
}

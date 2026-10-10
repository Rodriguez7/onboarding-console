"use client";

import Link from "next/link";
import { DragEvent, useEffect, useRef, useState } from "react";
import { Badge, Card, ErrorBanner, Stat, useAction, useLoad } from "@/components/ui";
import { useWorkspace } from "@/components/WorkspaceContext";
import { api, json } from "@/lib/api";
import type { ImportJob, ImportJobCreated, ImportRow, PlatformField } from "@/lib/types";

type Suggestion = ImportJobCreated["suggested_mapping"];

export default function ImportPage() {
  const { ws, refresh } = useWorkspace();
  const schema = useLoad(() => api<PlatformField[]>("/schema"), []);
  const jobs = useLoad(() => api<ImportJob[]>(`/workspaces/${ws.id}/imports`), [ws.id]);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [suggested, setSuggested] = useState<Suggestion | null>(null);
  const [samples, setSamples] = useState<Record<string, string>[]>([]);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [drag, setDrag] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const upload = useAction();
  const apply = useAction();
  const commit = useAction();

  // Resume the most recent import when arriving on the page.
  useEffect(() => {
    if (job || !jobs.data?.length) return;
    const latest = jobs.data[0];
    setJob(latest);
    setMapping(latest.mapping);
    api<ImportRow[]>(`/workspaces/${ws.id}/imports/${latest.id}/rows?limit=5`).then((rows) =>
      setSamples(rows.map((r) => r.raw)),
    );
  }, [jobs.data, job, ws.id]);

  async function onFile(file: File | undefined) {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    const created = await upload.run(() =>
      api<ImportJobCreated>(`/workspaces/${ws.id}/imports`, { method: "POST", body: form }),
    );
    if (!created) return;
    setJob(created);
    setSuggested(created.suggested_mapping);
    setSamples(created.preview);
    setMapping(created.mapping);
    await refresh();
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDrag(false);
    void onFile(e.dataTransfer.files[0]);
  }

  async function applyMapping() {
    if (!job) return;
    const updated = await apply.run(() =>
      api<ImportJob>(`/workspaces/${ws.id}/imports/${job.id}/mapping`, json({ mapping }, "PUT")),
    );
    if (updated) {
      setJob(updated);
      await refresh();
    }
  }

  async function commitImport() {
    if (!job) return;
    const updated = await commit.run(() =>
      api<ImportJob>(`/workspaces/${ws.id}/imports/${job.id}/commit`, { method: "POST" }),
    );
    if (updated) {
      setJob(updated);
      await refresh();
    }
  }

  const fields = schema.data ?? [];
  const targets = Object.values(mapping).filter(Boolean) as string[];
  const missingRequired = fields.filter((f) => f.required && !targets.includes(f.name));
  const dupes = new Set(targets.filter((t, i) => targets.indexOf(t) !== i));
  const locked = job?.status === "committed";

  return (
    <>
      <Card title="1. Upload customer CSV">
        <ErrorBanner error={upload.error} />
        <div
          className={`dropzone ${drag ? "drag" : ""}`}
          onClick={() => fileInput.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && fileInput.current?.click()}
        >
          {upload.busy ? "Uploading…" : "Drop a .csv file here, or click to choose one"}
          <div className="muted">UTF-8, comma/semicolon/tab separated, up to 5 MB</div>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,text/csv"
            hidden
            data-testid="csv-input"
            onChange={(e) => {
              void onFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </div>
        {jobs.data && jobs.data.length > 1 && (
          <p className="muted">
            {jobs.data.length} imports in this workspace — showing {job?.filename}.
          </p>
        )}
      </Card>

      {job && (
        <Card
          title={`2. Map fields — ${job.filename}`}
          actions={<Badge tone={locked ? "good" : job.status === "validated" ? "info" : "neutral"}>{job.status}</Badge>}
        >
          <ErrorBanner error={apply.error} />
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source column</th>
                  <th>Sample values</th>
                  <th style={{ width: 240 }}>Platform field</th>
                </tr>
              </thead>
              <tbody>
                {job.headers.map((h) => {
                  const s = suggested?.[h];
                  return (
                    <tr key={h}>
                      <td>
                        <code>{h}</code>
                      </td>
                      <td className="subtle">
                        {samples
                          .map((r) => r[h])
                          .filter(Boolean)
                          .slice(0, 3)
                          .join(" · ") || "—"}
                      </td>
                      <td>
                        <div className="row">
                          <select
                            aria-label={`Map ${h}`}
                            value={mapping[h] ?? ""}
                            disabled={locked}
                            onChange={(e) => setMapping({ ...mapping, [h]: e.target.value || null })}
                          >
                            <option value="">— Don&apos;t import —</option>
                            {fields.map((f) => (
                              <option key={f.name} value={f.name}>
                                {f.label}
                                {f.required ? " *" : ""}
                              </option>
                            ))}
                          </select>
                          {mapping[h] && dupes.has(mapping[h]!) && <Badge tone="critical">duplicate</Badge>}
                          {s?.field && s.field === mapping[h] && s.confidence < 1 && (
                            <Badge tone="warning">{Math.round(s.confidence * 100)}% match</Badge>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="row" style={{ marginTop: 12, justifyContent: "space-between" }}>
            <div className="muted">
              {missingRequired.length
                ? `Required fields still unmapped: ${missingRequired.map((f) => f.label).join(", ")}`
                : "All required fields are mapped."}
            </div>
            <button className="primary" onClick={applyMapping} disabled={locked || apply.busy}>
              {apply.busy ? "Validating…" : "Apply mapping & validate"}
            </button>
          </div>
        </Card>
      )}

      {job && job.status !== "uploaded" && (
        <Card title="3. Review & commit">
          <ErrorBanner error={commit.error} />
          <div className="stats">
            <Stat label="Rows" value={job.row_count} />
            <Stat label="Valid" value={job.valid_count} />
            <Stat
              label="Failed"
              value={job.invalid_count}
              hint={job.invalid_count ? <Link href={`/workspaces/${ws.id}/issues`}>Fix failed records →</Link> : null}
            />
            <Stat label="Committed" value={job.committed_count} />
          </div>
          {locked ? (
            <div className="banner banner-good">
              {job.committed_count} records loaded into the platform.{" "}
              {job.invalid_count > 0 && `${job.invalid_count} failed records were skipped.`}
            </div>
          ) : (
            <div className="row">
              <button className="primary" onClick={commitImport} disabled={commit.busy || job.valid_count === 0}>
                {commit.busy ? "Committing…" : `Commit ${job.valid_count} valid records`}
              </button>
              {job.invalid_count > 0 && (
                <span className="muted">Failed records will be skipped unless fixed first.</span>
              )}
            </div>
          )}
        </Card>
      )}

      <Card title="Platform schema">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Field</th>
                <th>Type</th>
                <th>Rules</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((f) => (
                <tr key={f.name}>
                  <td>
                    <code>{f.name}</code> {f.required && <Badge tone="info">required</Badge>}
                  </td>
                  <td>{f.type}</td>
                  <td className="subtle">{f.options.length ? `One of: ${f.options.join(", ")}` : f.description || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Card, ErrorBanner, useLoad } from "@/components/ui";
import { useWorkspace } from "@/components/WorkspaceContext";
import { api } from "@/lib/api";

export default function HandoverPage() {
  const { ws } = useWorkspace();
  const doc = useLoad(() => api<{ filename: string; markdown: string }>(`/workspaces/${ws.id}/handover`), [ws.id]);

  function download() {
    if (!doc.data) return;
    const url = URL.createObjectURL(new Blob([doc.data.markdown], { type: "text/markdown" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: doc.data.filename });
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Card
      title="Handover document"
      actions={
        <>
          <button onClick={() => doc.reload()}>Regenerate</button>
          <button onClick={() => window.print()}>Print / PDF</button>
          <button className="primary" onClick={download} disabled={!doc.data}>
            Download .md
          </button>
        </>
      }
    >
      <ErrorBanner error={doc.error} />
      {ws.blockers.length > 0 && (
        <div className="banner banner-info">
          This document is generated live from the workspace. It will list outstanding blockers until go-live.
        </div>
      )}
      {doc.data ? (
        <article className="markdown" data-testid="handover">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{doc.data.markdown}</ReactMarkdown>
        </article>
      ) : (
        <p className="muted">Generating…</p>
      )}
    </Card>
  );
}

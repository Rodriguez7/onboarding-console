export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details: string[] = [],
  ) {
    super(message);
  }
}

/** Turn FastAPI's various `detail` shapes into a message plus bullet points. */
function parseDetail(detail: unknown): { message: string; details: string[] } {
  if (typeof detail === "string") return { message: detail, details: [] };
  if (Array.isArray(detail)) {
    // Pydantic validation errors
    return {
      message: "Please check the highlighted values",
      details: detail.map((d: { loc?: unknown[]; msg?: string }) =>
        `${(d.loc ?? []).filter((p) => p !== "body").join(".")}: ${d.msg ?? ""}`,
      ),
    };
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; problems?: string[]; blockers?: string[] };
    return { message: d.message ?? "Request failed", details: d.problems ?? d.blockers ?? [] };
  }
  return { message: "Request failed", details: [] };
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...(isForm || !init.body ? {} : { "Content-Type": "application/json" }), ...init.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    let body: { detail?: unknown } = {};
    try {
      body = await res.json();
    } catch {
      /* non-JSON error */
    }
    const { message, details } = parseDetail(body.detail);
    throw new ApiError(message || `HTTP ${res.status}`, res.status, details);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const json = (body: unknown, method = "POST"): RequestInit => ({ method, body: JSON.stringify(body) });

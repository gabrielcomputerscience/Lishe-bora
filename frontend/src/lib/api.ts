// Browser-side API client. Requests go to /api/v1/* on the same origin (proxied to FastAPI by next.config.mjs).
// Auth uses httpOnly cookies set by the backend; on 401 we try one silent refresh.

export type ApiErrorBody = { code: string; message: string; details: Array<Record<string, unknown>> };

export class ApiError extends Error {
  status: number; code: string; details: ApiErrorBody["details"]; correlationId?: string;
  constructor(status: number, body: Partial<ApiErrorBody>, correlationId?: string) {
    super(body.message || "Something went wrong.");
    this.status = status; this.code = body.code || "HTTP_ERROR"; this.details = body.details || []; this.correlationId = correlationId;
  }
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const d of this.details) if (typeof d.field === "string") out[d.field] = String(d.message ?? "");
    return out;
  }
}

const BASE = "/api/v1";
let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  refreshing ??= fetch(`${BASE}/auth/refresh`, { method: "POST", credentials: "include" })
    .then((r) => r.ok).catch(() => false).finally(() => { setTimeout(() => (refreshing = null), 0); });
  return refreshing;
}

type Opts = Omit<RequestInit, "body"> & { body?: unknown; retry?: boolean };

export async function api<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  const { body, retry = true, headers, ...rest } = opts;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    ...rest,
    headers: { ...(isForm || body === undefined ? {} : { "Content-Type": "application/json" }), ...headers },
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  });
  if (res.status === 401 && retry && !path.startsWith("/auth/refresh") && !path.startsWith("/auth/login") && !path.startsWith("/auth/admin/login")) {
    if (await tryRefresh()) return api<T>(path, { ...opts, retry: false });
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, data?.error ?? {}, data?.correlation_id);
  return data as T;
}

export const get = <T,>(p: string) => api<T>(p);
export const post = <T,>(p: string, body?: unknown) => api<T>(p, { method: "POST", body });
export const put = <T,>(p: string, body?: unknown) => api<T>(p, { method: "PUT", body });
export const patch = <T,>(p: string, body?: unknown) => api<T>(p, { method: "PATCH", body });
export const del = <T,>(p: string) => api<T>(p, { method: "DELETE" });

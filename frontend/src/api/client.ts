export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function csrfToken(): string | undefined {
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith("es_csrf="))
    ?.split("=")[1];
}

async function ensureCsrf(): Promise<string | undefined> {
  let t = csrfToken();
  if (!t) {
    await fetch("/api/auth/csrf", { credentials: "same-origin" });
    t = csrfToken();
  }
  return t;
}

type Opts = { method?: string; body?: unknown; form?: FormData; params?: Record<string, string | number | boolean | undefined | null> };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const method = opts.method ?? (opts.body || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (method !== "GET") {
    const t = await ensureCsrf();
    if (t) headers["X-CSRF-Token"] = t;
  }
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let url = `/api${path}`;
  if (opts.params) {
    const q = new URLSearchParams();
    Object.entries(opts.params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
    });
    const s = q.toString();
    if (s) url += `?${s}`;
  }
  let res: Response;
  try {
    res = await fetch(url, { method, headers, body, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "We could not reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith("/auth/")) window.dispatchEvent(new Event("es:unauthorized"));
    let msg = `Something went wrong (${res.status}).`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d: any) => `${(d.loc || []).slice(-1)[0] ?? ""}: ${d.msg}`).join("; ");
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/**
 * fetch wrapper for /api. The session cookie is httpOnly; mutating calls add the CSRF
 * token that /api/auth/me hands out (kept here once the auth query has loaded it).
 */
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

let csrf = "";
export function setCsrf(token: string) { csrf = token; }

let onUnauthorized: (() => void) | null = null;
/** Called when a request comes back 401 (session expired): the auth gate refetches /me. */
export function setOnUnauthorized(fn: () => void) { onUnauthorized = fn; }

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["content-type"] = "application/json";
  if (method !== "GET") headers["x-csrf-token"] = csrf;
  const res = await fetch(url, {
    method, headers, credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = res.headers.get("content-type")?.includes("application/json") ? await res.json() : null;
  if (!res.ok) {
    if (res.status === 401 && !url.startsWith("/api/auth/") && !url.startsWith("/api/vault")) onUnauthorized?.();
    throw new ApiError(res.status, data?.error ?? res.statusText);
  }
  return data as T;
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T = { ok: true }>(url: string, body: unknown = {}) => request<T>("POST", url, body),
  put: <T = { ok: true }>(url: string, body: unknown = {}) => request<T>("PUT", url, body),
  patch: <T = { ok: true }>(url: string, body: unknown = {}) => request<T>("PATCH", url, body),
  delete: <T = { ok: true }>(url: string) => request<T>("DELETE", url),
};

export function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null) p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

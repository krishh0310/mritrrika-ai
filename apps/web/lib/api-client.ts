/**
 * The single path from the browser to FastAPI (§5).
 *
 * Every network call in the app goes through `api`. That is what makes two
 * rules enforceable rather than aspirational:
 *
 *   1. No route builds its own fetch, so no route can quietly skip the
 *      Authorization header or invent a different error shape.
 *   2. A 401 refreshes once and retries once. Never twice -- a refresh loop
 *      against an expired session would hammer the API and leave the user
 *      staring at a spinner instead of the login screen.
 *
 * The client holds a token; it does NOT hold authority. Roles and permissions
 * are re-read server-side on every request (§12), so anything this file
 * believes about the user is a hint for rendering, never a grant.
 */

import { clearSession, readSession, writeSession } from "./session";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** A failed call, carrying enough for a screen to render a useful state (§85). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** The caller is not signed in, or their session expired. */
  get isUnauthenticated() {
    return this.status === 401;
  }

  /** Signed in, but not permitted. Distinct from unauthenticated (§36). */
  get isForbidden() {
    return this.status === 403;
  }

  get isNotFound() {
    return this.status === 404;
  }

  /** The server could not be reached at all. */
  get isOffline() {
    return this.status === 0;
  }
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  /** Send as multipart rather than JSON. Used for uploads (§21). */
  form?: FormData;
  signal?: AbortSignal;
  /** Skip the Authorization header. Only login and refresh set this. */
  anonymous?: boolean;
  /** Return the body as text instead of parsing JSON (CSV exports). */
  raw?: boolean;
};

async function toApiError(response: Response): Promise<ApiError> {
  let detail: unknown;
  let message = response.statusText || `Request failed (${response.status})`;
  try {
    const body = await response.json();
    detail = body;
    if (typeof body?.detail === "string") {
      message = body.detail;
    } else if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      // FastAPI validation errors arrive as a list of field problems.
      message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    }
  } catch {
    // A non-JSON error body (a proxy page, say) leaves the status text.
  }
  return new ApiError(response.status, message, detail);
}

/** Exchange the refresh token for a new pair. Returns false if it cannot. */
async function refreshSession(): Promise<boolean> {
  const session = readSession();
  if (!session?.refreshToken) return false;

  try {
    const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: session.refreshToken }),
    });
    if (!response.ok) return false;

    const tokens = await response.json();
    writeSession({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
    });
    return true;
  } catch {
    return false;
  }
}

async function send<T>(path: string, options: RequestOptions, retry: boolean): Promise<T> {
  const headers: Record<string, string> = {};
  if (!options.form) headers["Content-Type"] = "application/json";

  if (!options.anonymous) {
    const token = readSession()?.accessToken;
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.form ?? (options.body ? JSON.stringify(options.body) : undefined),
      signal: options.signal,
    });
  } catch (cause) {
    // Distinguish "the API is down" from "the API said no". A screen that
    // conflates them tells the user to log in when the server is simply off.
    throw new ApiError(
      0,
      "Cannot reach the Mrittika API. Check that the server is running.",
      cause,
    );
  }

  if (response.status === 401 && retry && !options.anonymous) {
    if (await refreshSession()) {
      return send<T>(path, options, false);
    }
    clearSession();
    throw new ApiError(401, "Your session has expired. Sign in again.");
  }

  if (!response.ok) throw await toApiError(response);

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (options.raw) return text as T;
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => send<T>(path, { signal }, true),

  /** An authenticated download, as text. */
  text: (path: string) => send<string>(path, { raw: true }, true),

  post: <T>(path: string, body?: unknown) => send<T>(path, { method: "POST", body }, true),

  patch: <T>(path: string, body?: unknown) =>
    send<T>(path, { method: "PATCH", body }, true),

  /** Multipart upload. The browser sets the boundary, so no Content-Type here. */
  upload: <T>(path: string, form: FormData) =>
    send<T>(path, { method: "POST", form }, true),

  /** Login and refresh only -- they must not carry a stale bearer token. */
  anonymousPost: <T>(path: string, body: unknown) =>
    send<T>(path, { method: "POST", body, anonymous: true }, false),
};

/** Build a query string, dropping empty values so filters stay optional. */
export function query(params: Record<string, string | number | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}

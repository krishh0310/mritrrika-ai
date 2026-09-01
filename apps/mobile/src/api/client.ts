/**
 * The mobile client's single path to FastAPI (§5).
 *
 * Mirrors apps/web/lib/api-client.ts deliberately -- same refresh-once rule,
 * same error shape -- so the two clients cannot drift on what a 401 means. It
 * is a separate file rather than a shared package because the storage layer
 * differs: the browser uses sessionStorage, the phone uses SecureStore.
 *
 * §4 is explicit that mobile must not duplicate business logic. Nothing here
 * decides anything; it moves bytes and attaches a token.
 */

import Constants from "expo-constants";

import { clearTokens, readTokens, writeTokens } from "../storage/session";

/**
 * Where the API lives.
 *
 * `EXPO_PUBLIC_API_URL` wins when set -- that is Expo's own mechanism for
 * build-time configuration, and it lets a TestFlight or field build point at a
 * real server without editing app.json. Otherwise `extra.apiUrl`. The default
 * is localhost,
 * which is correct in a simulator and useless on a physical phone -- there,
 * localhost is the phone. So when the configured host is loopback we borrow
 * the LAN address Expo is already serving the bundle from, which is by
 * definition the developer's machine and reachable from the handset. A field
 * build sets `extra.apiUrl` explicitly and never takes this path.
 */
function resolveApiUrl(): string {
  const configured =
    process.env.EXPO_PUBLIC_API_URL ??
    (Constants.expoConfig?.extra?.apiUrl as string | undefined) ??
    "http://localhost:8000";

  if (!/^https?:\/\/(localhost|127\.0\.0\.1)(:|$)/.test(configured)) {
    return configured;
  }

  // "192.168.1.14:8081" -- the dev server's host and its own port.
  const hostUri = Constants.expoConfig?.hostUri;
  const host = hostUri?.split(":")[0];
  if (!host || host === "localhost" || host === "127.0.0.1") return configured;

  // Parsed by hand: React Native's URL polyfill has historically been
  // incomplete about `.port`, and this runs on every app start.
  const port = /^https?:\/\/[^/:]+:(\d+)/.exec(configured)?.[1] ?? "8000";
  return `http://${host}:${port}`;
}

export const API_URL = resolveApiUrl();

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isUnauthenticated() {
    return this.status === 401;
  }

  get isForbidden() {
    return this.status === 403;
  }

  /** No route to the API. Distinct from "the API said no" (§60). */
  get isOffline() {
    return this.status === 0;
  }
}

type Options = {
  method?: string;
  body?: unknown;
  form?: FormData;
  anonymous?: boolean;
};

async function refresh(): Promise<boolean> {
  const tokens = await readTokens();
  if (!tokens?.refreshToken) return false;
  try {
    const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refreshToken }),
    });
    if (!response.ok) return false;
    const next = await response.json();
    await writeTokens({
      accessToken: next.access_token,
      refreshToken: next.refresh_token,
    });
    return true;
  } catch {
    return false;
  }
}

async function send<T>(path: string, options: Options, retry: boolean): Promise<T> {
  const headers: Record<string, string> = {};
  if (!options.form) headers["Content-Type"] = "application/json";

  if (!options.anonymous) {
    const tokens = await readTokens();
    if (tokens?.accessToken) headers.Authorization = `Bearer ${tokens.accessToken}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.form ?? (options.body ? JSON.stringify(options.body) : undefined),
    });
  } catch {
    throw new ApiError(0, "No connection to the Mrittika server.");
  }

  if (response.status === 401 && retry && !options.anonymous) {
    if (await refresh()) return send<T>(path, options, false);
    await clearTokens();
    throw new ApiError(401, "Your session has expired. Sign in again.");
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string) => send<T>(path, {}, true),
  post: <T>(path: string, body?: unknown) => send<T>(path, { method: "POST", body }, true),
  upload: <T>(path: string, form: FormData) =>
    send<T>(path, { method: "POST", form }, true),
  anonymousPost: <T>(path: string, body: unknown) =>
    send<T>(path, { method: "POST", body, anonymous: true }, false),
};

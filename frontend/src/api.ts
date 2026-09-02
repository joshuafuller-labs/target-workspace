// Thin fetch wrapper around the Target Workspace API.
// Session cookie auth — credentials: "include" on every request.

import type {
  AuditEventOut,
  ApiTokenCreated,
  ApiTokenListItem,
  Board,
  BoardCreatePayload,
  ObservationOut,
  Target,
  TargetCreatePayload,
  TargetUpdatePayload,
  UserCreatePayload,
  UserListItem,
  UserOut,
  UserUpdatePayload,
  PasskeyOut,
  PluginCatalog,
  PublisherConfig,
  PublisherConfigPayload,
  SourceConfig,
  SourceConfigPayload,
} from "./types";

// Vite dev server proxies /v1, /healthz, /readyz to the backend on :8000.
// In production the backend serves the SPA from the same origin.
const BASE = "";

class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = await res.json();
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Auth
  login: (identifier: string, password: string) =>
    request<UserOut>("POST", "/v1/auth/login", { email: identifier, password }),
  logout: () => request<{ status: string }>("POST", "/v1/auth/logout"),
  me: () => request<UserOut>("GET", "/v1/auth/me"),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<UserOut>("POST", "/v1/auth/change-password", {
      current_password: currentPassword,
      new_password: newPassword,
    }),
  // tw-ptn2 / tw-ypfy: revoke every existing session for this user.
  revokeAllSessions: () =>
    request<{ status: string }>("POST", "/v1/auth/sessions/revoke-all"),
  enrollTotp: () =>
    request<{ secret: string; provisioning_uri: string }>(
      "POST",
      "/v1/auth/mfa/totp/enroll",
    ),
  verifyTotpEnroll: (code: string) =>
    request<{ mfa_enabled: boolean }>("POST", "/v1/auth/mfa/totp/verify-enroll", {
      code,
    }),
  disableTotp: (password: string, code: string) =>
    request<{ mfa_enabled: boolean }>("POST", "/v1/auth/mfa/totp/disable", {
      password,
      code,
    }),
  listPasskeys: () => request<PasskeyOut[]>("GET", "/v1/auth/passkeys"),
  listApiTokens: () => request<ApiTokenListItem[]>("GET", "/v1/auth/tokens"),
  createApiToken: (name: string, scopes: string[]) =>
    request<ApiTokenCreated>("POST", "/v1/auth/tokens", { name, scopes }),
  revokeApiToken: (id: string) => request<void>("DELETE", `/v1/auth/tokens/${id}`),
  passkeyRegistrationOptions: (name: string) =>
    request<{ publicKey: Record<string, unknown> }>(
      "POST",
      "/v1/auth/passkeys/register/options",
      { name },
    ),
  verifyPasskeyRegistration: (
    name: string,
    challenge: string,
    credential: Record<string, unknown>,
  ) =>
    request<PasskeyOut>("POST", "/v1/auth/passkeys/register/verify", {
      name,
      challenge,
      credential,
    }),
  passkeyAuthenticationOptions: () =>
    request<{ publicKey: Record<string, unknown> }>(
      "POST",
      "/v1/auth/passkeys/authenticate/options",
    ),
  verifyPasskeyAuthentication: (
    challenge: string,
    credential: Record<string, unknown>,
  ) =>
    request<UserOut>("POST", "/v1/auth/passkeys/authenticate/verify", {
      challenge,
      credential,
    }),
  deletePasskey: (id: string) => request<void>("DELETE", `/v1/auth/passkeys/${id}`),

  // Plugin configuration
  listPlugins: () => request<PluginCatalog>("GET", "/v1/plugins"),
  listSources: () => request<SourceConfig[]>("GET", "/v1/sources"),
  createSource: (payload: SourceConfigPayload) =>
    request<SourceConfig>("POST", "/v1/sources", payload),
  updateSource: (id: string, payload: SourceConfigPayload) =>
    request<SourceConfig>("PATCH", `/v1/sources/${id}`, payload),
  deleteSource: (id: string) => request<void>("DELETE", `/v1/sources/${id}`),
  testSource: (id: string, payload: Record<string, unknown>) =>
    request<{ normalized: Record<string, unknown> }>(
      "POST",
      `/v1/sources/${id}/test`,
      { payload },
    ),
  listPublishers: () => request<PublisherConfig[]>("GET", "/v1/publishers"),
  createPublisher: (payload: PublisherConfigPayload) =>
    request<PublisherConfig>("POST", "/v1/publishers", payload),
  updatePublisher: (id: string, payload: PublisherConfigPayload) =>
    request<PublisherConfig>("PATCH", `/v1/publishers/${id}`, payload),
  deletePublisher: (id: string) => request<void>("DELETE", `/v1/publishers/${id}`),

  // Boards
  listBoards: () => request<Board[]>("GET", "/v1/boards"),
  createBoard: (payload: BoardCreatePayload) =>
    request<Board>("POST", "/v1/boards", payload),
  getBoard: (id: string) => request<Board>("GET", `/v1/boards/${id}`),
  updateBoard: (
    id: string,
    payload: {
      name?: string;
      theme?: "neutral" | "tactical" | "federal" | "sar" | "ics";
      transitions?: "unrestricted" | "sequential";
    },
  ) => request<Board>("PATCH", `/v1/boards/${id}`, payload),
  deleteBoard: (id: string) =>
    request<void>("DELETE", `/v1/boards/${id}`),

  // Targets
  listTargets: (boardId: string, columnId?: string) => {
    const qs = new URLSearchParams({ board_id: boardId });
    if (columnId) qs.set("column_id", columnId);
    return request<Target[]>("GET", `/v1/targets?${qs.toString()}`);
  },
  createTarget: (payload: TargetCreatePayload) =>
    request<Target>("POST", "/v1/targets", payload),
  getTarget: (id: string) => request<Target>("GET", `/v1/targets/${id}`),
  updateTarget: (id: string, payload: TargetUpdatePayload) =>
    request<Target>("PATCH", `/v1/targets/${id}`, payload),
  moveTarget: (
    id: string,
    columnId: string,
    opts?: { justification?: string; approving_role?: string },
  ) =>
    request<Target>("POST", `/v1/targets/${id}/move`, {
      column_id: columnId,
      ...opts,
    }),
  reorderTarget: (id: string, columnId: string, afterId: string | null) =>
    request<Target>("POST", `/v1/targets/${id}/reorder`, {
      column_id: columnId,
      after_id: afterId,
    }),

  // tw-ip0: per-target observation timeline
  listObservations: (id: string) =>
    request<ObservationOut[]>("GET", `/v1/targets/${id}/observations`),

  // tw-6uz8 / tw-gaf4: presence lookups
  getPresence: (callsign: string) =>
    request<{
      callsign: string;
      lat: number;
      lon: number;
      hae: number | null;
      ce: number | null;
      le: number | null;
      time: string;
      course: number | null;
      speed: number | null;
      source: string | null;
    }>("GET", `/v1/presence/${encodeURIComponent(callsign)}`),
  // tw-smc: workspace settings (admin-mutable)
  getWorkspace: () =>
    request<{
      id: string;
      name: string;
      brand_name: string | null;
      default_theme: string;
      freshness_active_seconds: number;
      freshness_coasting_seconds: number;
      freshness_stale_seconds: number;
      correlation_radius_m: number;
    }>("GET", "/v1/workspaces/me"),
  patchWorkspace: (payload: {
    brand_name?: string | null;
    default_theme?: string;
    freshness_active_seconds?: number;
    freshness_coasting_seconds?: number;
    freshness_stale_seconds?: number;
    correlation_radius_m?: number;
  }) =>
    request<{
      id: string;
      name: string;
      brand_name: string | null;
      default_theme: string;
      freshness_active_seconds: number;
      freshness_coasting_seconds: number;
      freshness_stale_seconds: number;
      correlation_radius_m: number;
    }>("PATCH", "/v1/workspaces/me", payload),

  // tw-43c2: full presence snapshot (all currently online callsigns)
  listPresence: () =>
    request<
      Array<{
        callsign: string;
        lat: number;
        lon: number;
        hae: number | null;
        ce: number | null;
        le: number | null;
        time: string;
        course: number | null;
        speed: number | null;
        source: string | null;
      }>
    >("GET", "/v1/presence"),

  // Users
  listUsers: () => request<UserListItem[]>("GET", "/v1/users"),
  createUser: (payload: UserCreatePayload) =>
    request<UserListItem>("POST", "/v1/users", payload),
  updateUser: (id: string, payload: UserUpdatePayload) =>
    request<UserListItem>("PATCH", `/v1/users/${id}`, payload),
  disableUser: (id: string) =>
    request<UserListItem>("POST", `/v1/users/${id}/disable`),
  enableUser: (id: string) =>
    request<UserListItem>("POST", `/v1/users/${id}/enable`),
  deleteUser: (id: string) => request<void>("DELETE", `/v1/users/${id}`),

  // Meta
  healthz: () =>
    request<{ status: string; version: string }>("GET", "/healthz"),

  // Audit
  listAudit: (targetId?: string) => {
    const qs = new URLSearchParams();
    if (targetId) qs.set("target_id", targetId);
    return request<AuditEventOut[]>(
      "GET",
      `/v1/audit${qs.toString() ? `?${qs.toString()}` : ""}`,
    );
  },
};

export { ApiError };

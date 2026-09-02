// TypeScript types mirroring the FastAPI OpenAPI schemas.
// Hand-curated for MVP; codegen from /v1/openapi.json is a post-MVP improvement.

export type UUID = string;

export interface UserOut {
  id: UUID;
  email: string;
  display_name: string;
  role: string;
  must_change_password?: boolean;
  mfa_enabled?: boolean;
  tak_callsign?: string | null;
}

export interface UserListItem {
  id: UUID;
  email: string;
  display_name: string;
  role: string;
  enabled: boolean;
  created_at: string;
}

export interface PasskeyOut {
  id: UUID;
  name: string;
  created_at: string;
  last_used_at: string | null;
  aaguid: string | null;
}

export interface ApiTokenListItem {
  id: UUID;
  name: string;
  role: string;
  scopes: string[];
  preview: string;
  expires_at: string | null;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface ApiTokenCreated {
  id: UUID;
  name: string;
  token: string;
  role: string;
  scopes: string[];
  preview: string;
  expires_at: string | null;
}

export interface PluginInfo {
  name: string;
  kind: "source" | "publisher" | "effector" | string;
}

export interface PluginCatalog {
  sources: PluginInfo[];
  publishers: PluginInfo[];
  effectors: PluginInfo[];
}

export interface SourceConfig {
  id: UUID;
  name: string;
  plugin_type: string;
  enabled: boolean;
  adapter_config: Record<string, unknown>;
  normalization_map: Record<string, unknown>;
  promotion_policy_id: UUID | null;
}

export interface SourceConfigPayload {
  name: string;
  plugin_type: string;
  enabled: boolean;
  adapter_config: Record<string, unknown>;
  normalization_map: Record<string, unknown>;
  promotion_policy_id: UUID | null;
}

export interface PublisherConfig {
  id: UUID;
  name: string;
  plugin_type: string;
  enabled: boolean;
  adapter_config: Record<string, unknown>;
  column_filter_ids: UUID[];
}

export interface PublisherConfigPayload {
  name: string;
  plugin_type: string;
  enabled: boolean;
  adapter_config: Record<string, unknown>;
  column_filter_ids: UUID[];
}

export interface UserCreatePayload {
  email: string;
  display_name: string;
  role: string;
  password: string;
}

export interface UserUpdatePayload {
  display_name?: string;
  role?: string;
}

export interface Column {
  id: UUID;
  name: string;
  order: number;
  wip_limit: number | null;
  color: string | null;
  requires_approval: boolean;
}

export type ThemeName = "neutral" | "tactical" | "federal" | "sar" | "ics";

export interface Board {
  id: UUID;
  name: string;
  columns: Column[];
  transitions: "unrestricted" | "sequential";
  theme: ThemeName;
}

export type GeometryKind = "point" | "ellipse" | "polygon";

export type GeometryQuality =
  | "bearing-only"
  | "single-source"
  | "corroborated"
  | "confirmed";

export interface Ellipse {
  semi_major_m: number;
  semi_minor_m: number;
  bearing_deg: number;
}

export interface Target {
  id: UUID;
  name: string;
  cot_type: string;
  category: string | null;
  lat: number;
  lon: number;
  hae: number | null;
  ce: number | null;
  le: number | null;
  time: string;
  stale: string | null;
  confidence: number | null;
  version: number;
  remarks: string | null;
  source: string | null;
  geometry_kind: GeometryKind;
  geometry_quality: GeometryQuality;
  ellipse: Ellipse | null;
  polygon_vertices: Array<[number, number]> | null;
  custom_fields: Record<string, unknown>;
  assigned_callsigns?: string[];
}

export interface TargetUpdatePayload {
  name?: string;
  cot_type?: string;
  category?: string | null;
  // Geometry — backend accepts these on PATCH (tw-znu).
  lat?: number;
  lon?: number;
  hae?: number | null;
  ce?: number | null;
  le?: number | null;
  confidence?: number | null;
  remarks?: string | null;
  source?: string | null;
  geometry_kind?: GeometryKind;
  geometry_quality?: GeometryQuality;
  ellipse?: Ellipse | null;
  polygon_vertices?: Array<[number, number]> | null;
}

export interface AuditEventOut {
  id: UUID;
  target_id: UUID;
  actor_id: UUID;
  event_type: string;
  occurred_at: string;
  from_column_id: UUID | null;
  to_column_id: UUID | null;
  justification: string | null;
  metadata: Record<string, unknown>;
}

export interface ObservationOut {
  id: UUID;
  observed_at: string;
  lat: number;
  lon: number;
  hae: number | null;
  ce: number | null;
  confidence: number | null;
  source: string | null;
  classification: string | null;
}

export interface TargetCreatePayload {
  board_id: UUID;
  column_id: UUID;
  name: string;
  cot_type?: string;
  category?: string | null;
  lat: number;
  lon: number;
  hae?: number | null;
  ce?: number | null;
  le?: number | null;
  time: string;
  stale?: string | null;
  confidence?: number | null;
  remarks?: string | null;
  source?: string | null;
  geometry_kind?: GeometryKind;
  geometry_quality?: GeometryQuality;
  ellipse?: Ellipse | null;
  polygon_vertices?: Array<[number, number]> | null;
  custom_fields?: Record<string, unknown>;
}

export interface BoardCreatePayload {
  name: string;
  columns: Array<{
    name: string;
    order: number;
    wip_limit?: number | null;
    color?: string | null;
    requires_approval?: boolean;
  }>;
  transitions?: "unrestricted" | "sequential";
}

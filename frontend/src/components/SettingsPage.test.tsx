import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { SettingsPage } from "./SettingsPage";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    api: {
      listBoards: vi.fn().mockResolvedValue([]),
      getWorkspace: vi.fn().mockResolvedValue({
        id: "workspace-1",
        name: "Workspace",
        brand_name: null,
        default_theme: "neutral",
        freshness_active_seconds: 15,
        freshness_coasting_seconds: 60,
        freshness_stale_seconds: 180,
        correlation_radius_m: 100,
      }),
      listPlugins: vi.fn(),
      listSources: vi.fn(),
      createSource: vi.fn(),
      updateSource: vi.fn(),
      deleteSource: vi.fn(),
      testSource: vi.fn(),
      listPublishers: vi.fn(),
      createPublisher: vi.fn(),
      updatePublisher: vi.fn(),
      deletePublisher: vi.fn(),
    },
  };
});

const admin = {
  id: "user-1",
  email: "admin@example.com",
  display_name: "Admin",
  role: "admin",
  must_change_password: false,
  mfa_enabled: false,
};

describe("SettingsPage plugin config", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listPlugins).mockResolvedValue({
      sources: [
        { name: "manual", kind: "source" },
        { name: "http_webhook", kind: "source" },
      ],
      publishers: [
        { name: "raw_cot", kind: "publisher" },
        { name: "tak_server", kind: "publisher" },
      ],
      effectors: [{ name: "manual_effector", kind: "effector" }],
    });
    vi.mocked(api.listSources).mockResolvedValue([
      {
        id: "source-1",
        name: "Webhook In",
        plugin_type: "http_webhook",
        enabled: true,
        adapter_config: { token_ref: "webhook-token" },
        normalization_map: { name: "$.callsign" },
        promotion_policy_id: null,
      },
    ]);
    vi.mocked(api.listPublishers).mockResolvedValue([
      {
        id: "publisher-1",
        name: "TAK Lab",
        plugin_type: "tak_server",
        enabled: true,
        adapter_config: { host: "tak.example.invalid" },
        column_filter_ids: [],
      },
    ]);
  });

  it("renders Sources and Publishers tabs under Settings for admins", async () => {
    render(<SettingsPage user={admin} />);

    expect(screen.getByRole("button", { name: "Sources" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Publishers" })).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Sources" }));

    expect(await screen.findByText("Webhook In")).toBeVisible();
    expect(screen.getByLabelText("Source name")).toHaveValue("Webhook In");
    expect(screen.getAllByText("http_webhook").length).toBeGreaterThan(0);
  });

  it("creates and tests a source from Settings", async () => {
    vi.mocked(api.createSource).mockResolvedValueOnce({
      id: "source-2",
      name: "Manual Source",
      plugin_type: "manual",
      enabled: true,
      adapter_config: { token_ref: "webhook-token" },
      normalization_map: {},
      promotion_policy_id: null,
    });
    vi.mocked(api.testSource).mockResolvedValueOnce({
      normalized: { name: "ALPHA-1" },
    });
    render(<SettingsPage user={admin} />);
    await userEvent.click(screen.getByRole("button", { name: "Sources" }));

    await userEvent.clear(await screen.findByLabelText("Source name"));
    await userEvent.type(screen.getByLabelText("Source name"), "Manual Source");
    await userEvent.selectOptions(screen.getByLabelText("Source plugin"), "manual");
    await userEvent.click(screen.getByRole("button", { name: "Create source" }));

    expect(api.createSource).toHaveBeenCalledWith({
      name: "Manual Source",
      plugin_type: "manual",
      enabled: true,
      adapter_config: { token_ref: "webhook-token" },
      normalization_map: { name: "$.callsign" },
      promotion_policy_id: null,
    });

    await userEvent.click(screen.getByRole("button", { name: "Test source" }));

    expect(api.testSource).toHaveBeenCalledWith("source-1", {
      callsign: "ALPHA-1",
      location: { lat: 30, lon: -97 },
    });
    expect(await screen.findByText(/ALPHA-1/)).toBeVisible();
  });

  it("updates a publisher from Settings", async () => {
    vi.mocked(api.updatePublisher).mockResolvedValueOnce({
      id: "publisher-1",
      name: "Raw CoT",
      plugin_type: "raw_cot",
      enabled: true,
      adapter_config: { transport: "udp" },
      column_filter_ids: [],
    });
    render(<SettingsPage user={admin} />);
    await userEvent.click(screen.getByRole("button", { name: "Publishers" }));

    await userEvent.clear(await screen.findByLabelText("Publisher name"));
    await userEvent.type(screen.getByLabelText("Publisher name"), "Raw CoT");
    await userEvent.selectOptions(screen.getByLabelText("Publisher plugin"), "raw_cot");
    await userEvent.click(screen.getByRole("button", { name: "Update publisher" }));

    await waitFor(() =>
      expect(api.updatePublisher).toHaveBeenCalledWith("publisher-1", {
        name: "Raw CoT",
        plugin_type: "raw_cot",
        enabled: true,
        adapter_config: { host: "tak.example.invalid" },
        column_filter_ids: [],
      }),
    );
  });
});

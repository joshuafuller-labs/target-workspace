import React, { useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { BRAND_NAME } from "../brand";
import { navigate } from "../router";
import type { ApiTokenListItem, PasskeyOut, UserOut } from "../types";
import { credentialToJSON, toCreationOptions } from "../webauthn";

interface Props {
  user: UserOut;
}

const TOKEN_SCOPE_OPTIONS = [
  "boards:read",
  "boards:write",
  "targets:read",
  "targets:write",
  "audit:read",
  "users:read",
  "users:write",
  "resources:read",
  "resources:write",
  "groups:read",
  "groups:write",
  "op_periods:read",
  "op_periods:write",
  "positions:read",
  "positions:write",
  "presence:read",
  "publishers:read",
  "metrics:read",
  "templates:read",
  "templates:write",
  "forms:read",
  "invitations:write",
  "safety:read",
  "workspace:read",
  "workspace:write",
  "workspace:export",
  "workflow:read",
  "workflow:write",
  "tokens:read",
  "tokens:write",
];

export function AccountSecurityPage({ user }: Props): React.JSX.Element {
  return (
    <main
      className="min-h-screen"
      style={{ background: "var(--tw-bg)", color: "var(--tw-ink)" }}
    >
      <header
        className="tw-rail px-4 desktop:px-6 py-3 border-b sticky top-0 z-20 flex items-center gap-3"
        style={{
          background: "var(--tw-bg-panel)",
          borderColor: "var(--tw-border)",
        }}
      >
        <button
          onClick={() => navigate("/settings")}
          className="tw-eyebrow text-[11px] px-3"
          style={outlineButton}
        >
          Settings
        </button>
        <div className="flex-1 min-w-0">
          <p className="tw-eyebrow text-[10px]" style={{ color: "var(--tw-brand)" }}>
            {BRAND_NAME}
          </p>
          <h1 className="tw-display text-lg desktop:text-xl truncate">
            Account & Security
          </h1>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-4 desktop:px-6 py-6">
        <AccountSecurityContent user={user} showHeading={false} />
      </div>
    </main>
  );
}

export function AccountSecurityContent({
  user,
  showHeading = true,
}: Props & { showHeading?: boolean }): React.JSX.Element {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [totpSecret, setTotpSecret] = useState<string | null>(null);
  const [totpUri, setTotpUri] = useState<string | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [totpPassword, setTotpPassword] = useState("");
  const [totpMessage, setTotpMessage] = useState<string | null>(null);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [passkeys, setPasskeys] = useState<PasskeyOut[]>([]);
  const [apiTokens, setApiTokens] = useState<ApiTokenListItem[]>([]);
  const [apiTokenName, setApiTokenName] = useState("");
  const [apiTokenScopes, setApiTokenScopes] = useState<string[]>([]);
  const [newApiTokenPlaintext, setNewApiTokenPlaintext] = useState<string | null>(null);
  const [passkeyName, setPasskeyName] = useState("");
  const [passkeyMessage, setPasskeyMessage] = useState<string | null>(null);
  const [tokenMessage, setTokenMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    void refreshPasskeys();
    void refreshApiTokens();
  }, []);

  async function refreshPasskeys(): Promise<void> {
    setPasskeys(await api.listPasskeys());
  }

  async function refreshApiTokens(): Promise<void> {
    setApiTokens(await api.listApiTokens());
  }

  async function changePassword(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setBusy("password");
    setPasswordMessage(null);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setPasswordMessage("Password changed.");
    } catch (error) {
      setPasswordMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  async function enrollTotp(): Promise<void> {
    setBusy("totp-enroll");
    setTotpMessage(null);
    try {
      const response = await api.enrollTotp();
      setTotpSecret(response.secret);
      setTotpUri(response.provisioning_uri);
    } catch (error) {
      setTotpMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  async function verifyTotp(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setBusy("totp-verify");
    setTotpMessage(null);
    try {
      await api.verifyTotpEnroll(totpCode);
      setTotpCode("");
      setTotpMessage("Two-factor authentication enabled.");
    } catch (error) {
      setTotpMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  async function disableTotp(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setBusy("totp-disable");
    setTotpMessage(null);
    try {
      await api.disableTotp(totpPassword, totpCode);
      setTotpPassword("");
      setTotpCode("");
      setTotpMessage("Two-factor authentication disabled.");
    } catch (error) {
      setTotpMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  async function revokeAllSessions(): Promise<void> {
    setBusy("sessions");
    setSessionMessage(null);
    try {
      await api.revokeAllSessions();
      setSessionMessage("Sessions revoked.");
    } catch (error) {
      setSessionMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  async function registerPasskey(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (!window.PublicKeyCredential || !navigator.credentials) {
      setPasskeyMessage("Passkeys are not available in this browser.");
      return;
    }
    const name = passkeyName.trim() || "Passkey";
    setBusy("passkey-register");
    setPasskeyMessage(null);
    try {
      const options = await api.passkeyRegistrationOptions(name);
      const credential = await navigator.credentials.create({
        publicKey: toCreationOptions(options.publicKey),
      });
      if (!credential) throw new Error("Passkey registration was cancelled.");
      await api.verifyPasskeyRegistration(
        name,
        String(options.publicKey.challenge),
        credentialToJSON(credential),
      );
      setPasskeyName("");
      await refreshPasskeys();
      setPasskeyMessage("Passkey registered.");
    } catch (error) {
      setPasskeyMessage(`Passkey registration failed: ${errorMessage(error)}`);
    } finally {
      setBusy(null);
    }
  }

  async function deletePasskey(id: string): Promise<void> {
    setBusy(`passkey-delete-${id}`);
    setPasskeyMessage(null);
    try {
      await api.deletePasskey(id);
      await refreshPasskeys();
      setPasskeyMessage("Passkey removed.");
    } catch (error) {
      setPasskeyMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  async function revokeApiToken(token: ApiTokenListItem): Promise<void> {
    setBusy(`api-token-revoke-${token.id}`);
    setTokenMessage(null);
    try {
      await api.revokeApiToken(token.id);
      await refreshApiTokens();
      setTokenMessage("API token revoked.");
    } catch (error) {
      setTokenMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  function toggleApiTokenScope(scope: string): void {
    setApiTokenScopes((current) =>
      current.includes(scope)
        ? current.filter((item) => item !== scope)
        : [...current, scope],
    );
  }

  async function createApiToken(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setBusy("api-token-create");
    setTokenMessage(null);
    setNewApiTokenPlaintext(null);
    try {
      const created = await api.createApiToken(apiTokenName.trim(), apiTokenScopes);
      setApiTokenName("");
      setApiTokenScopes([]);
      setNewApiTokenPlaintext(created.token);
      await refreshApiTokens();
      setTokenMessage("API token created.");
    } catch (error) {
      setTokenMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      {showHeading && <h2 className="text-lg font-semibold">Account & Security</h2>}
        <Panel title="Profile">
          <Row label="Display name">
            <span>{user.display_name}</span>
          </Row>
          <Row label="Login identifier">
            <code style={mono}>{user.email}</code>
          </Row>
          <Row label="Role">
            <code style={mono}>{user.role}</code>
          </Row>
        </Panel>

        <Panel title="Passkeys">
          <form onSubmit={(event) => void registerPasskey(event)} className="space-y-3">
            <LabeledInput
              id="passkey-name"
              label="Passkey name"
              value={passkeyName}
              onChange={setPasskeyName}
            />
            <button
              type="submit"
              disabled={busy !== null}
              className="tw-eyebrow px-3 py-2"
              style={primaryButton}
            >
              {busy === "passkey-register" ? "Registering..." : "Register passkey"}
            </button>
          </form>
          {passkeys.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--tw-ink-muted)" }}>
              No passkeys registered.
            </p>
          ) : (
            <div className="space-y-2">
              {passkeys.map((passkey) => (
                <div
                  key={passkey.id}
                  className="flex items-center justify-between gap-3 px-3 py-2"
                  style={{
                    background: "var(--tw-bg)",
                    borderWidth: 1,
                    borderStyle: "solid",
                    borderColor: "var(--tw-border)",
                    borderRadius: "var(--tw-radius)",
                  }}
                >
                  <div className="min-w-0">
                    <div className="text-sm truncate">{passkey.name}</div>
                    <div className="text-[11px]" style={{ color: "var(--tw-ink-dim)" }}>
                      {passkey.last_used_at ? "Used" : "Not used"}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void deletePasskey(passkey.id)}
                    disabled={busy !== null}
                    className="tw-eyebrow px-3 py-2 text-[11px]"
                    style={outlineButton}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}
          {passkeyMessage && <Message text={passkeyMessage} />}
        </Panel>

        <Panel title="Password">
          <form onSubmit={(event) => void changePassword(event)} className="space-y-3">
            <LabeledInput
              id="current-password"
              label="Current password"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={setCurrentPassword}
            />
            <LabeledInput
              id="new-password"
              label="New password"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={setNewPassword}
            />
            <button type="submit" disabled={busy !== null} className="tw-eyebrow px-3 py-2" style={primaryButton}>
              {busy === "password" ? "Saving..." : "Change password"}
            </button>
          </form>
          {passwordMessage && <Message text={passwordMessage} />}
        </Panel>

        <Panel title="Two-factor authentication">
          <Row label="Status">
            <span>{user.mfa_enabled ? "Enabled" : "Not enabled"}</span>
          </Row>
          {!user.mfa_enabled && (
            <>
              <button
                type="button"
                onClick={() => void enrollTotp()}
                disabled={busy !== null}
                className="tw-eyebrow px-3 py-2"
                style={outlineButton}
              >
                {busy === "totp-enroll" ? "Starting..." : "Start TOTP enrollment"}
              </button>
              {totpSecret && (
                <div className="space-y-3">
                  <Row label="Secret">
                    <code style={mono}>{totpSecret}</code>
                  </Row>
                  {totpUri && (
                    <Row label="URI">
                      <code className="break-all" style={mono}>
                        {totpUri}
                      </code>
                    </Row>
                  )}
                  <form onSubmit={(event) => void verifyTotp(event)} className="space-y-3">
                    <LabeledInput
                      id="totp-code"
                      label="TOTP code"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      value={totpCode}
                      onChange={setTotpCode}
                    />
                    <button type="submit" disabled={busy !== null} className="tw-eyebrow px-3 py-2" style={primaryButton}>
                      Verify
                    </button>
                  </form>
                </div>
              )}
            </>
          )}
          {user.mfa_enabled && (
            <form onSubmit={(event) => void disableTotp(event)} className="space-y-3">
              <LabeledInput
                id="totp-password"
                label="Password"
                type="password"
                autoComplete="current-password"
                value={totpPassword}
                onChange={setTotpPassword}
              />
              <LabeledInput
                id="totp-disable-code"
                label="TOTP code"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={totpCode}
                onChange={setTotpCode}
              />
              <button type="submit" disabled={busy !== null} className="tw-eyebrow px-3 py-2" style={outlineButton}>
                Disable TOTP
              </button>
            </form>
          )}
          {totpMessage && <Message text={totpMessage} />}
        </Panel>

        <Panel title="Active sessions">
          <Row label="Current session">
            <span>Signed in</span>
          </Row>
          <button
            type="button"
            onClick={() => void revokeAllSessions()}
            disabled={busy !== null}
            className="tw-eyebrow px-3 py-2"
            style={outlineButton}
          >
            {busy === "sessions" ? "Revoking..." : "Revoke all sessions"}
          </button>
          {sessionMessage && <Message text={sessionMessage} />}
        </Panel>

        <Panel title="API tokens">
          <form onSubmit={(event) => void createApiToken(event)} className="space-y-3">
            <LabeledInput
              id="api-token-name"
              label="Token name"
              value={apiTokenName}
              onChange={setApiTokenName}
            />
            <div className="grid grid-cols-1 desktop:grid-cols-2 gap-2">
              {TOKEN_SCOPE_OPTIONS.map((scope) => (
                <label
                  key={scope}
                  className="flex items-center gap-2 text-sm"
                  style={{ minHeight: 32 }}
                >
                  <input
                    type="checkbox"
                    checked={apiTokenScopes.includes(scope)}
                    onChange={() => toggleApiTokenScope(scope)}
                  />
                  <code style={mono}>{scope}</code>
                </label>
              ))}
            </div>
            <button
              type="submit"
              disabled={busy !== null || apiTokenName.trim().length === 0 || apiTokenScopes.length === 0}
              className="tw-eyebrow px-3 py-2"
              style={primaryButton}
            >
              {busy === "api-token-create" ? "Creating..." : "Create API token"}
            </button>
          </form>
          {newApiTokenPlaintext && (
            <Row label="New token">
              <code className="break-all" style={mono}>
                {newApiTokenPlaintext}
              </code>
            </Row>
          )}
          {apiTokens.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--tw-ink-muted)" }}>
              No API tokens created.
            </p>
          ) : (
            <div className="space-y-2">
              {apiTokens.map((token) => (
                <div
                  key={token.id}
                  className="grid gap-3 desktop:grid-cols-[minmax(0,1fr)_auto] desktop:items-center px-3 py-2"
                  style={{
                    background: "var(--tw-bg)",
                    borderWidth: 1,
                    borderStyle: "solid",
                    borderColor: "var(--tw-border)",
                    borderRadius: "var(--tw-radius)",
                  }}
                >
                  <div className="min-w-0 space-y-2">
                    <div className="text-sm font-medium truncate">{token.name}</div>
                    <div className="flex flex-wrap gap-1">
                      {token.scopes.map((scope) => (
                        <code
                          key={scope}
                          className="px-2 py-1 text-[11px]"
                          style={{
                            ...mono,
                            background: "var(--tw-bg-panel)",
                            borderRadius: "var(--tw-radius)",
                          }}
                        >
                          {scope}
                        </code>
                      ))}
                    </div>
                    <div className="text-[11px]" style={{ color: "var(--tw-ink-dim)" }}>
                      Preview {token.preview} · {token.revoked_at ? "Revoked" : "Active"}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void revokeApiToken(token)}
                    disabled={busy !== null || token.revoked_at !== null}
                    className="tw-eyebrow px-3 py-2 text-[11px]"
                    style={outlineButton}
                    aria-label={`Revoke ${token.name}`}
                  >
                    Revoke
                  </button>
                </div>
              ))}
            </div>
          )}
          {tokenMessage && <Message text={tokenMessage} />}
        </Panel>

        {(user.role === "admin" || user.role === "commander") && (
          <Panel title="Admin recovery">
            <Row label="Users">
              <button
                type="button"
                onClick={() => navigate("/settings")}
                className="tw-eyebrow px-3 py-2"
                style={outlineButton}
              >
                Open user administration
              </button>
            </Row>
          </Panel>
        )}
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (
      typeof error.detail === "object" &&
      error.detail !== null &&
      "detail" in error.detail
    ) {
      return String((error.detail as { detail: unknown }).detail);
    }
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
}

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section
      className="space-y-3 p-4"
      style={{
        background: "var(--tw-bg-panel)",
        borderWidth: 1,
        borderStyle: "solid",
        borderColor: "var(--tw-border)",
        borderRadius: "var(--tw-radius)",
      }}
    >
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="grid grid-cols-1 desktop:grid-cols-[180px_1fr] gap-2 text-sm">
      <div className="tw-eyebrow text-[10px]" style={{ color: "var(--tw-ink-dim)" }}>
        {label}
      </div>
      <div>{children}</div>
    </div>
  );
}

function LabeledInput({
  id,
  label,
  value,
  onChange,
  type = "text",
  autoComplete,
  inputMode,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  autoComplete?: string;
  inputMode?: React.HTMLAttributes<HTMLInputElement>["inputMode"];
}): React.JSX.Element {
  return (
    <label className="block space-y-1" htmlFor={id}>
      <span className="tw-eyebrow text-[10px]" style={{ color: "var(--tw-ink-dim)" }}>
        {label}
      </span>
      <input
        id={id}
        type={type}
        value={value}
        autoComplete={autoComplete}
        inputMode={inputMode}
        onChange={(event) => onChange(event.target.value)}
        className="w-full px-3 py-2 text-sm"
        style={{
          background: "var(--tw-bg)",
          color: "var(--tw-ink)",
          borderWidth: 1,
          borderStyle: "solid",
          borderColor: "var(--tw-border)",
          borderRadius: "var(--tw-radius)",
          minHeight: 44,
        }}
      />
    </label>
  );
}

function Message({ text }: { text: string }): React.JSX.Element {
  return (
    <p className="text-sm" style={{ color: "var(--tw-ink-muted)" }}>
      {text}
    </p>
  );
}

const mono: React.CSSProperties = {
  fontFamily: "var(--tw-font-mono)",
  color: "var(--tw-accent)",
  fontSize: 13,
};

const outlineButton: React.CSSProperties = {
  background: "var(--tw-bg-panel)",
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--tw-border)",
  borderRadius: "var(--tw-radius)",
  color: "var(--tw-ink)",
  minHeight: 44,
};

const primaryButton: React.CSSProperties = {
  background: "var(--tw-accent-bg)",
  color: "var(--tw-accent-ink)",
  borderRadius: "var(--tw-radius)",
  minHeight: 44,
};

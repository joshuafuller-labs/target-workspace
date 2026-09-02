import React from "react";
import { useState } from "react";

import { api, ApiError } from "../api";

const ROLES = [
  "viewer",
  "observer",
  "operator",
  "approver",
  "commander",
  "admin",
] as const;

interface Props {
  onCreated: () => Promise<void> | void;
  onCancel: () => void;
  /** Whether the logged-in user can mint another admin. The backend
   *  enforces this too; the UI just hides the option for clarity. */
  callerIsAdmin: boolean;
}

/** Modal form for POST /v1/users. Admin-tier role hidden from the
 *  dropdown unless the caller is admin themselves (anti-escalation). */
export function NewUserForm({
  onCreated,
  onCancel,
  callerIsAdmin,
}: Props): React.JSX.Element {
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<string>("viewer");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const visibleRoles = callerIsAdmin
    ? ROLES
    : ROLES.filter((r) => r !== "admin");

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createUser({
        email,
        display_name: displayName,
        role,
        password,
      });
      await onCreated();
    } catch (err) {
      setError(extract(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-label="Create new user"
      onClick={onCancel}
      className="fixed top-0 left-0 w-[100dvw] h-[100dvh] z-50 flex items-end justify-center desktop:items-center desktop:p-4"
      style={{ background: "rgba(0,0,0,0.7)" }}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="w-full max-w-md max-h-[92vh] overflow-y-auto p-4 desktop:p-6 space-y-4 rounded-t-[var(--tw-radius)] desktop:rounded-[var(--tw-radius)]"
        style={{
          background: "var(--tw-bg)",
          borderWidth: 1,
          borderStyle: "solid",
          borderColor: "var(--tw-border)",
        }}
      >
        <header>
          <p
            className="tw-eyebrow text-[10px]"
            style={{ color: "var(--tw-brand)" }}
          >
            New user
          </p>
          <h2 className="tw-display text-lg desktop:text-xl mt-0.5">
            Provision an account
          </h2>
          <p className="text-[11px] mt-1" style={{ color: "var(--tw-ink-dim)" }}>
            Sets an initial password. Force-change-on-first-login lands
            with tw-4exk.
          </p>
        </header>

        <Labeled label="Email" id="nu-email">
          <input
            id="nu-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2"
            style={inputStyle}
          />
        </Labeled>
        <Labeled label="Display name" id="nu-name">
          <input
            id="nu-name"
            required
            minLength={1}
            maxLength={200}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full px-3 py-2"
            style={inputStyle}
          />
        </Labeled>
        <Labeled label="Role" id="nu-role">
          <select
            id="nu-role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-full px-3 py-2"
            style={inputStyle}
          >
            {visibleRoles.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </Labeled>
        <Labeled label="Initial password" id="nu-pw">
          <input
            id="nu-pw"
            type="text"
            required
            minLength={1}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2"
            style={{ ...inputStyle, fontFamily: "var(--tw-font-mono)" }}
          />
        </Labeled>

        {error && (
          <p
            className="text-sm px-3 py-2"
            style={{
              background: "var(--tw-bg-panel)",
              borderLeftWidth: 3,
              borderLeftStyle: "solid",
              borderLeftColor: "var(--tw-approval)",
              color: "var(--tw-approval)",
            }}
          >
            {error}
          </p>
        )}

        <footer className="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="tw-eyebrow text-[11px] px-3"
            style={{
              color: "var(--tw-ink-muted)",
              background: "transparent",
              minHeight: 44,
            }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy}
            className="tw-eyebrow text-[11px] px-4"
            style={{
              background: "var(--tw-accent-bg)",
              color: "var(--tw-accent-ink)",
              borderRadius: "var(--tw-radius)",
              minHeight: 44,
            }}
          >
            {busy ? "Creating…" : "Create"}
          </button>
        </footer>
      </form>
    </div>
  );
}

function extract(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "object" && err.detail && "detail" in err.detail) {
      return String((err.detail as { detail: unknown }).detail);
    }
    return err.message;
  }
  return String(err);
}

const inputStyle: React.CSSProperties = {
  background: "var(--tw-bg-panel)",
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--tw-border)",
  borderRadius: "var(--tw-radius)",
  color: "var(--tw-ink)",
  fontFamily: "var(--tw-font-body)",
  minHeight: 44,
};

function Labeled({
  label,
  id,
  children,
}: {
  label: string;
  id: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <label htmlFor={id} className="block space-y-1">
      <span
        className="tw-eyebrow text-[10px]"
        style={{ color: "var(--tw-ink-dim)" }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}

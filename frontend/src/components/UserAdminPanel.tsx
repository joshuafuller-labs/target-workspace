import React from "react";
import { useEffect, useState } from "react";

import { api, ApiError } from "../api";
import type { UserListItem, UserOut } from "../types";
import { NewUserForm } from "./NewUserForm";

const ROLES = [
  "viewer",
  "observer",
  "operator",
  "approver",
  "commander",
  "admin",
] as const;

interface Props {
  /** The logged-in user — for self-protection (don't let admin delete
   *  themselves accidentally) and role-gating delete affordances. */
  me: UserOut;
}

/** Settings → Users panel. Lists workspace users, lets commander+
 *  create / rename / re-role / disable / enable. Admin additionally
 *  gets the delete affordance. Consumer of the /v1/users API. */
export function UserAdminPanel({ me }: Props): React.JSX.Element {
  const [users, setUsers] = useState<UserListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());

  const isAdmin = me.role === "admin";

  async function refresh(): Promise<void> {
    try {
      setUsers(await api.listUsers());
    } catch (err) {
      setError(extract(err));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function setBusy(id: string, on: boolean): Promise<void> {
    setBusyIds((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function doDisable(u: UserListItem): Promise<void> {
    await setBusy(u.id, true);
    try {
      await api.disableUser(u.id);
      await refresh();
    } catch (err) {
      setError(extract(err));
    } finally {
      await setBusy(u.id, false);
    }
  }
  async function doEnable(u: UserListItem): Promise<void> {
    await setBusy(u.id, true);
    try {
      await api.enableUser(u.id);
      await refresh();
    } catch (err) {
      setError(extract(err));
    } finally {
      await setBusy(u.id, false);
    }
  }
  async function doRoleChange(u: UserListItem, role: string): Promise<void> {
    await setBusy(u.id, true);
    try {
      await api.updateUser(u.id, { role });
      await refresh();
    } catch (err) {
      setError(extract(err));
    } finally {
      await setBusy(u.id, false);
    }
  }
  async function doDelete(u: UserListItem): Promise<void> {
    if (!window.confirm(`Delete ${u.email}? This is a soft delete.`)) return;
    await setBusy(u.id, true);
    try {
      await api.deleteUser(u.id);
      await refresh();
    } catch (err) {
      setError(extract(err));
    } finally {
      await setBusy(u.id, false);
    }
  }

  return (
    <section
      className="space-y-3"
      style={{
        background: "var(--tw-bg-panel)",
        borderWidth: 1,
        borderStyle: "solid",
        borderColor: "var(--tw-border)",
        borderRadius: "var(--tw-radius)",
        padding: 16,
      }}
    >
      <header className="flex items-baseline justify-between gap-3">
        <div>
          <h2 className="tw-display text-base" style={{ color: "var(--tw-ink)" }}>
            Workspace users
          </h2>
          <p className="text-[11px]" style={{ color: "var(--tw-ink-dim)" }}>
            Provision accounts, change roles, and revoke access without
            touching the database.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowNewForm(true)}
          className="tw-eyebrow text-[11px] px-3"
          style={{
            background: "var(--tw-accent-bg)",
            color: "var(--tw-accent-ink)",
            borderRadius: "var(--tw-radius)",
            minHeight: 44,
          }}
        >
          + New user
        </button>
      </header>

      {error && (
        <div
          className="text-sm px-3 py-2"
          style={{
            background: "var(--tw-bg)",
            borderLeftWidth: 3,
            borderLeftStyle: "solid",
            borderLeftColor: "var(--tw-approval)",
            color: "var(--tw-approval)",
          }}
        >
          {error}
        </div>
      )}

      {users === null ? (
        <p className="text-[12px]" style={{ color: "var(--tw-ink-dim)" }}>
          Loading…
        </p>
      ) : users.length === 0 ? (
        <p className="text-[12px]" style={{ color: "var(--tw-ink-dim)" }}>
          No users yet.
        </p>
      ) : (
        <ul className="space-y-2">
          {users.map((u) => {
            const busy = busyIds.has(u.id);
            const isSelf = u.id === me.id;
            return (
              <li
                key={u.id}
                className="px-3 py-2 flex flex-wrap items-center gap-3"
                style={{
                  background: "var(--tw-bg)",
                  borderWidth: 1,
                  borderStyle: "solid",
                  borderColor: "var(--tw-border)",
                  borderRadius: "var(--tw-radius)",
                  opacity: u.enabled ? 1 : 0.55,
                }}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">
                    {u.display_name}
                  </div>
                  <div
                    className="text-[11px] truncate"
                    style={{
                      color: "var(--tw-ink-dim)",
                      fontFamily: "var(--tw-font-mono)",
                    }}
                  >
                    {u.email}
                    {!u.enabled && (
                      <span
                        className="tw-eyebrow text-[9px] ml-2"
                        style={{ color: "var(--tw-approval)" }}
                      >
                        DISABLED
                      </span>
                    )}
                  </div>
                </div>
                <label className="flex items-center gap-1 text-[11px]">
                  <span
                    className="tw-eyebrow text-[9px]"
                    style={{ color: "var(--tw-ink-dim)" }}
                  >
                    Role
                  </span>
                  <select
                    value={u.role}
                    onChange={(e) => void doRoleChange(u, e.target.value)}
                    disabled={busy || isSelf}
                    aria-label={`Role for ${u.email}`}
                    className="px-2 py-1 text-sm"
                    style={{
                      background: "var(--tw-bg-panel)",
                      borderWidth: 1,
                      borderStyle: "solid",
                      borderColor: "var(--tw-border)",
                      borderRadius: "var(--tw-radius)",
                      color: "var(--tw-ink)",
                      minHeight: 36,
                    }}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </label>
                {u.enabled ? (
                  <button
                    type="button"
                    onClick={() => void doDisable(u)}
                    disabled={busy || isSelf}
                    className="tw-eyebrow text-[10px] px-3"
                    style={{
                      color: "var(--tw-approval)",
                      borderWidth: 1,
                      borderStyle: "solid",
                      borderColor: "var(--tw-approval)",
                      borderRadius: "var(--tw-radius)",
                      background: "transparent",
                      minHeight: 36,
                    }}
                  >
                    Disable
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void doEnable(u)}
                    disabled={busy}
                    className="tw-eyebrow text-[10px] px-3"
                    style={{
                      color: "var(--tw-accent)",
                      borderWidth: 1,
                      borderStyle: "solid",
                      borderColor: "var(--tw-accent)",
                      borderRadius: "var(--tw-radius)",
                      background: "transparent",
                      minHeight: 36,
                    }}
                  >
                    Enable
                  </button>
                )}
                {isAdmin && !isSelf && (
                  <button
                    type="button"
                    onClick={() => void doDelete(u)}
                    disabled={busy}
                    className="tw-eyebrow text-[10px] px-3"
                    style={{
                      color: "var(--tw-ink-dim)",
                      borderWidth: 1,
                      borderStyle: "solid",
                      borderColor: "var(--tw-border)",
                      borderRadius: "var(--tw-radius)",
                      background: "transparent",
                      minHeight: 36,
                    }}
                    title="Soft delete — user data is preserved for audit chain"
                  >
                    Delete
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {showNewForm && (
        <NewUserForm
          onCreated={async () => {
            setShowNewForm(false);
            await refresh();
          }}
          onCancel={() => setShowNewForm(false)}
          callerIsAdmin={isAdmin}
        />
      )}
    </section>
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

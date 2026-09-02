import React from "react";
import { useState } from "react";

import { api, ApiError } from "../api";
import { BRAND_NAME } from "../brand";
import type { UserOut } from "../types";
import { credentialToJSON, toRequestOptions } from "../webauthn";

interface Props {
  onLogin: (user: UserOut) => void;
}

export function Login({ onLogin }: Props): React.JSX.Element {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const user = await api.login(identifier, password);
      onLogin(user);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          typeof err.detail === "object" && err.detail !== null && "detail" in err.detail
            ? String((err.detail as { detail: unknown }).detail)
            : err.message,
        );
      } else {
        setError(String(err));
      }
    } finally {
      setBusy(false);
    }
  }

  async function handlePasskeyLogin(): Promise<void> {
    setError(null);
    setBusy(true);
    try {
      if (!window.PublicKeyCredential || !navigator.credentials) {
        throw new Error("Passkeys are not available in this browser.");
      }
      const options = await api.passkeyAuthenticationOptions();
      const credential = await navigator.credentials.get({
        publicKey: toRequestOptions(options.publicKey),
      });
      if (!credential) throw new Error("Passkey sign-in was cancelled.");
      const user = await api.verifyPasskeyAuthentication(
        String(options.publicKey.challenge),
        credentialToJSON(credential),
      );
      onLogin(user);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          typeof err.detail === "object" && err.detail !== null && "detail" in err.detail
            ? String((err.detail as { detail: unknown }).detail)
            : err.message,
        );
      } else {
        setError(String(err));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-8 bg-neutral-950 text-neutral-100">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-neutral-900 border border-neutral-800 rounded-lg p-8 space-y-5"
      >
        <div>
          <p className="text-[11px] uppercase tracking-[0.32em] text-neutral-500">
            {BRAND_NAME}
          </p>
          <h1 className="text-2xl font-semibold mt-1">Sign in</h1>
        </div>

        <div className="space-y-2">
          <label
            htmlFor="login-identifier"
            className="block text-xs uppercase tracking-wider text-neutral-400"
          >
            Login identifier
          </label>
          <input
            id="login-identifier"
            type="text"
            autoComplete="username"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            className="w-full px-3 py-2 bg-neutral-950 border border-neutral-800 rounded text-neutral-100 focus:border-amber-500 focus:outline-none"
            required
          />
        </div>

        <div className="space-y-2">
          <label htmlFor="password" className="block text-xs uppercase tracking-wider text-neutral-400">
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 bg-neutral-950 border border-neutral-800 rounded text-neutral-100 focus:border-amber-500 focus:outline-none"
            required
          />
        </div>

        {error && (
          <p className="text-sm text-red-400 bg-red-950/30 border border-red-900/40 rounded px-3 py-2">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full py-2 bg-amber-500 hover:bg-amber-400 disabled:bg-neutral-700 text-neutral-950 font-semibold rounded transition"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <button
          type="button"
          onClick={() => void handlePasskeyLogin()}
          disabled={busy}
          className="w-full py-2 bg-neutral-950 hover:bg-neutral-800 disabled:bg-neutral-800 text-neutral-100 border border-neutral-700 font-semibold rounded transition"
        >
          Sign in with passkey
        </button>
      </form>
    </main>
  );
}

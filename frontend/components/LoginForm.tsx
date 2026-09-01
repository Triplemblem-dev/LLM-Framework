"use client";

import { useState } from "react";
import { setToken, verifyToken } from "../lib/api";

interface LoginFormProps {
  onSuccess: () => void;
}

export function LoginForm({ onSuccess }: LoginFormProps) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function submit() {
    const token = value.trim();
    if (!token || checking) return;
    setChecking(true);
    setError(null);
    const ok = await verifyToken(token);
    setChecking(false);
    if (!ok) {
      setError("That token was rejected by the backend.");
      return;
    }
    setToken(token);
    onSuccess();
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <h1>LLM Framework</h1>
        <div className="sub">
          Paste the APP_ACCESS_TOKEN from the .env file beside docker-compose.yml.
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div className="settings-field">
            <label>Access token</label>
            <input
              type="password"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="paste token"
              autoFocus
            />
          </div>
          <button className="btn-primary" type="submit" disabled={!value.trim() || checking}>
            {checking ? "Checking…" : "Connect"}
          </button>
          {error && <div className="error">{error}</div>}
        </form>
      </div>
    </div>
  );
}

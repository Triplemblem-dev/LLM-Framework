"use client";

import { useEffect, useState } from "react";
import { Workspace } from "../components/Workspace";
import { LoginForm } from "../components/LoginForm";
import { getToken, verifyToken } from "../lib/api";

type AuthStatus = "checking" | "authed" | "anon";

export default function Home() {
  const [status, setStatus] = useState<AuthStatus>("checking");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setStatus("anon");
      return;
    }
    verifyToken(token).then((ok) => setStatus(ok ? "authed" : "anon"));
  }, []);

  if (status === "checking") return null;
  if (status === "anon") return <LoginForm onSuccess={() => setStatus("authed")} />;
  return <Workspace />;
}

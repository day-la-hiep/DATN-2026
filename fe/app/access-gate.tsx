"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { AuthScreen } from "@/features/auth/components/AuthScreen";
import { AUTH_STATE_EVENT, getAccessToken } from "@/services/client";

export function AccessGate({ children }: { children: React.ReactNode }) {
  const isClient = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );

  const [hasToken, setHasToken] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return Boolean(getAccessToken());
  });

  useEffect(() => {
    const syncAuthState = () => setHasToken(Boolean(getAccessToken()));
    window.addEventListener(AUTH_STATE_EVENT, syncAuthState);
    return () => window.removeEventListener(AUTH_STATE_EVENT, syncAuthState);
  }, []);

  if (!isClient) return null;

  if (!hasToken) {
    return <AuthScreen onAuthenticated={() => setHasToken(true)} />;
  }

  return <>{children}</>;
}

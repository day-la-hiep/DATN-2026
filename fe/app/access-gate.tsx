"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AuthScreen } from "@/features/auth/components/AuthScreen";
import { AUTH_STATE_EVENT, getAccessToken, getAuthenticatedUser } from "@/services/client";

// Khu vực của từng vai trò; vào sai khu thì chuyển về trang chủ của vai trò đó.
const ROLE_HOME: Record<string, string> = { patient: "/chats", doctor: "/doctor", admin: "/doctor" };

function homeForPath(role: string, pathname: string): string | null {
  const home = ROLE_HOME[role] ?? "/chats";
  // khu /doctor gồm cả tư vấn và số hoá tài liệu nên admin cũng được vào
  const area = pathname.startsWith("/doctor") ? "doctor" : pathname.startsWith("/chats") ? "patient" : null;
  const allowed = area === "doctor" ? role === "doctor" || role === "admin" : area === role;
  return area !== null && !allowed ? home : null;
}

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

  const router = useRouter();
  const pathname = usePathname();
  const role = hasToken ? (getAuthenticatedUser()?.role ?? "patient") : null;
  const redirectTo = role ? homeForPath(role, pathname) : null;

  useEffect(() => {
    if (redirectTo) router.replace(redirectTo);
  }, [redirectTo, router]);

  if (!isClient) return null;

  if (!hasToken) {
    return <AuthScreen onAuthenticated={() => setHasToken(true)} />;
  }

  if (redirectTo) return null;

  return <>{children}</>;
}

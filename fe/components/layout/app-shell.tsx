"use client";

import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { ArrowLeft, LogOut, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { logout } from "@/features/auth/logout";
import { cn } from "@/lib/utils";
import { getAuthenticatedUser } from "@/services/client";

export interface ShellNavItem {
  href: string;
  label: string;
  hint: string;
  icon: LucideIcon;
  exact?: boolean;
}

interface AppShellProps {
  brandLabel: string;
  brandIcon: LucideIcon;
  navTitle: string;
  nav: ShellNavItem[];
  // trang 3 cột cần khung cao bằng màn hình; trang thường thì cuộn
  fullBleed?: boolean;
  children: React.ReactNode;
}

function isActive(pathname: string, href: string, exact?: boolean) {
  return exact ? pathname === href : pathname.startsWith(href);
}

function Brand({ href, label, icon: Icon }: { href: string; label: string; icon: LucideIcon }) {
  return (
    <Link href={href} className="flex items-center gap-2.5">
      <span className="flex size-8 items-center justify-center rounded-xl bg-brand/10 text-brand">
        <Icon className="size-4" />
      </span>
      <span className="text-sm font-semibold tracking-tight text-foreground">
        Derma AI <span className="font-normal text-muted-foreground">· {label}</span>
      </span>
    </Link>
  );
}

function AccountBar() {
  const account = getAuthenticatedUser();
  return (
    <div className="flex items-center justify-between gap-2 border-t border-border px-2.5 pt-3">
      <span className="truncate text-xs font-medium text-foreground">{account?.full_name || account?.username || "Tài khoản"}</span>
      <Button size="sm" variant="ghost" onClick={() => void logout()} className="h-7 gap-1.5 px-2 text-[11px] text-muted-foreground hover:text-foreground">
        <LogOut className="size-3.5" />
        Đăng xuất
      </Button>
    </div>
  );
}

export function AppShell({ brandLabel, brandIcon, navTitle, nav, fullBleed = false, children }: AppShellProps) {
  const pathname = usePathname();
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 5_000 } } })
  );
  const home = nav[0]?.href ?? "/";

  return (
    <QueryClientProvider client={client}>
      <div className={cn("flex bg-background", fullBleed ? "h-dvh overflow-hidden" : "min-h-screen")}>
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col gap-6 border-r border-border bg-card/40 px-3 py-4 md:flex">
          <div className="px-2">
            <Brand href={home} label={brandLabel} icon={brandIcon} />
          </div>
          <nav className="flex flex-1 flex-col gap-1" aria-label={navTitle}>
            <p className="px-2 pb-1 text-[11px] font-medium text-muted-foreground">{navTitle}</p>
            {nav.map(({ href, label, hint, icon: Icon, exact }) => {
              const active = isActive(pathname, href, exact);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2.5 rounded-xl px-2.5 py-2 transition-colors",
                    active ? "bg-brand/10 text-brand" : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <Icon className="size-4 shrink-0" />
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-medium">{label}</span>
                    <span className="block truncate text-[10px] opacity-70">{hint}</span>
                  </span>
                </Link>
              );
            })}
          </nav>
          <div className="space-y-1">
            <Link
              href="/chats"
              className="flex items-center gap-2 rounded-xl px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ArrowLeft className="size-3.5" /> Về trò chuyện
            </Link>
            <AccountBar />
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-border/80 bg-background/85 backdrop-blur-md md:hidden">
            <div className="flex h-14 items-center gap-3 px-4">
              <Brand href={home} label={brandLabel} icon={brandIcon} />
              <div className="flex-1" />
              <button type="button" onClick={() => void logout()} className="text-xs font-medium text-muted-foreground hover:text-foreground">
                Đăng xuất
              </button>
            </div>
            <nav className="flex gap-1 overflow-x-auto px-3 pb-2" aria-label={navTitle}>
              {nav.map(({ href, label, exact }) => (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "shrink-0 rounded-lg px-2.5 py-1.5 text-xs font-medium",
                    isActive(pathname, href, exact) ? "bg-brand/10 text-brand" : "text-muted-foreground"
                  )}
                >
                  {label}
                </Link>
              ))}
            </nav>
          </header>
          {fullBleed ? (
            <main className="min-h-0 flex-1">{children}</main>
          ) : (
            <main className="mx-auto w-full max-w-[96rem] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
          )}
        </div>
      </div>
    </QueryClientProvider>
  );
}

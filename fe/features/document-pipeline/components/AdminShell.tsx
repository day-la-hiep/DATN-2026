"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ArrowLeft, ListTree, type LucideIcon, Workflow } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/utils";

const NAV: { href: string; label: string; hint: string; icon: LucideIcon }[] = [
  { href: "/admin/documents", label: "Số hóa sách giáo khoa", hint: "Chuẩn bị tri thức cho trợ lý AI", icon: ListTree },
];

function Brand() {
  return (
    <Link href="/admin/documents" className="flex items-center gap-2.5">
      <span className="flex size-8 items-center justify-center rounded-xl bg-brand/10 text-brand">
        <Workflow className="size-4" />
      </span>
      <span className="text-sm font-semibold tracking-tight text-foreground">
        Derma AI <span className="font-normal text-muted-foreground">· Quản trị</span>
      </span>
    </Link>
  );
}

/** Khung chung của khu vực admin: cột trái điều hướng + nội dung chính bên phải (trên mobile cột trái thành thanh ngang). */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 5_000 } },
      })
  );

  return (
    <QueryClientProvider client={client}>
      <div className="flex min-h-screen bg-background">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col gap-6 border-r border-border bg-card/40 px-3 py-4 md:flex">
          <div className="px-2">
            <Brand />
          </div>
          <nav className="flex flex-1 flex-col gap-1" aria-label="Khu vực quản trị">
            <p className="px-2 pb-1 text-[11px] font-medium text-muted-foreground">Tài liệu y khoa</p>
            {NAV.map(({ href, label, hint, icon: Icon }) => {
              const active = pathname.startsWith(href);
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
          <Link
            href="/chats"
            className="flex items-center gap-2 rounded-xl px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" /> Về trò chuyện
          </Link>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-border/80 bg-background/85 backdrop-blur-md md:hidden">
            <div className="flex h-14 items-center gap-3 px-4">
              <Brand />
              <div className="flex-1" />
              <Link href="/chats" className="text-xs font-medium text-muted-foreground hover:text-foreground">
                Về trò chuyện
              </Link>
            </div>
            <nav className="flex gap-1 overflow-x-auto px-3 pb-2" aria-label="Khu vực quản trị">
              {NAV.map(({ href, label }) => (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "shrink-0 rounded-lg px-2.5 py-1.5 text-xs font-medium",
                    pathname.startsWith(href) ? "bg-brand/10 text-brand" : "text-muted-foreground"
                  )}
                >
                  {label}
                </Link>
              ))}
            </nav>
          </header>
          <main className="mx-auto w-full max-w-[96rem] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
        </div>
      </div>
    </QueryClientProvider>
  );
}

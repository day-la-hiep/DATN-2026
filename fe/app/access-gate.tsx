"use client";

import { useSyncExternalStore, useState } from "react";
import { getAccessToken, setAccessToken } from "@/services/client";
import { KeyRound } from "lucide-react";

/**
 * Gate đơn giản cho shared-token auth (bảo vệ bản demo khi deploy cho người ngoài
 * test — xem `core/app/core/auth.py`). KHÔNG phải màn hình đăng nhập thật: không
 * validate token với backend ở đây, chỉ lưu localStorage rồi để request thật tự 401
 * nếu sai (interceptor trong `services/client.ts` sẽ xoá + reload lại gate).
 */
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

  const [input, setInput] = useState("");

  if (!isClient) return null;

  if (!hasToken) {
    return (
      <div className="relative flex min-h-screen items-center justify-center bg-background p-4 overflow-hidden">
        {/* Ambient radial glow background */}
        <div className="pointer-events-none absolute inset-0 modern-dot-pattern opacity-40" />
        <div className="pointer-events-none absolute -top-40 -right-40 h-96 w-96 rounded-full bg-brand/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-40 -left-40 h-96 w-96 rounded-full bg-brand-secondary/10 blur-3xl" />

        <form
          onSubmit={(e) => {
            e.preventDefault();
            const trimmed = input.trim();
            if (!trimmed) return;
            setAccessToken(trimmed);
            setHasToken(true);
          }}
          className="relative flex w-full max-w-md flex-col gap-6 rounded-2xl border border-border bg-card/85 p-8 shadow-xl backdrop-blur-md"
        >
          {/* Header Badge */}
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-brand/20 bg-brand/10 px-3 py-1 font-mono text-[11px] font-medium text-brand">
              <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
              Bảo mật hệ thống
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              v1.0.0
            </span>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand/10 text-brand">
                <KeyRound className="size-4" />
              </div>
              <h1 className="font-serif text-2xl font-bold tracking-tight text-foreground">
                Xác thực truy cập
              </h1>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Hệ thống đang trong giai đoạn thử nghiệm lâm sàng. Vui lòng cung cấp mã bảo mật được cấp để tiếp tục.
            </p>
          </div>

          <div className="space-y-3">
            <input
              type="password"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Nhập mã truy cập..."
              autoFocus
              className="w-full h-11 rounded-xl border border-border bg-background px-4 font-mono text-sm text-foreground outline-none transition-all placeholder:text-muted-foreground/60 focus:border-brand focus:ring-2 focus:ring-brand/20"
            />

            <button
              type="submit"
              disabled={!input.trim()}
              className="flex w-full h-11 items-center justify-center rounded-xl bg-gradient-to-r from-brand to-brand-secondary font-medium text-sm text-white shadow-sm shadow-brand/25 transition-all hover:opacity-95 hover:-translate-y-0.5 active:scale-[0.99] disabled:pointer-events-none disabled:opacity-40 cursor-pointer"
            >
              Tiếp tục vào hệ thống →
            </button>
          </div>
        </form>
      </div>
    );
  }

  return <>{children}</>;
}

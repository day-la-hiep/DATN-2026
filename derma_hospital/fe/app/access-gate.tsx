"use client";

import { useEffect, useState } from "react";
import { getAccessToken, setAccessToken } from "@/services/client";

/**
 * Gate đơn giản cho shared-token auth (bảo vệ bản demo khi deploy cho người ngoài
 * test — xem `core/app/core/auth.py`). KHÔNG phải màn hình đăng nhập thật: không
 * validate token với backend ở đây, chỉ lưu localStorage rồi để request thật tự 401
 * nếu sai (interceptor trong `services/client.ts` sẽ xoá + reload lại gate).
 */
export function AccessGate({ children }: { children: React.ReactNode }) {
  const [hasToken, setHasToken] = useState<boolean | null>(null);
  const [input, setInput] = useState("");

  useEffect(() => {
    setHasToken(Boolean(getAccessToken()));
  }, []);

  // Chưa xác định xong (tránh flash gate lúc SSR/hydrate) -> không render gì.
  if (hasToken === null) return null;

  if (!hasToken) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const trimmed = input.trim();
            if (!trimmed) return;
            setAccessToken(trimmed);
            setHasToken(true);
          }}
          className="flex w-full max-w-sm flex-col gap-3 rounded-xl border border-border bg-card p-6 shadow-sm"
        >
          <h1 className="text-lg font-semibold text-foreground">Nhập mã truy cập</h1>
          <p className="text-sm text-muted-foreground">
            Ứng dụng đang ở chế độ thử nghiệm — nhập mã truy cập được cung cấp để tiếp
            tục.
          </p>
          <input
            type="password"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Access token"
            autoFocus
            className="rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-brand"
          />
          <button
            type="submit"
            disabled={!input.trim()}
            className="rounded-md bg-brand px-3 py-2 text-sm font-medium text-brand-foreground transition-opacity hover:opacity-90 disabled:opacity-50 cursor-pointer"
          >
            Tiếp tục
          </button>
        </form>
      </div>
    );
  }

  return <>{children}</>;
}

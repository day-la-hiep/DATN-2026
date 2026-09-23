"use client";

import { Menu, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useChatStore } from "../store";

export function ChatHeader({ onOpenSidebar }: { onOpenSidebar: () => void }) {
  const activeId = useChatStore((s) => s.activeId);
  const conversations = useChatStore((s) => s.conversations);
  const streaming = useChatStore((s) =>
    activeId ? s.hasActiveStream(activeId) : false
  );
  const conversation = conversations.find((c) => c.id === activeId);

  return (
    <header className="border-b border-border/80 bg-background/80 backdrop-blur-md px-4 py-3 sticky top-0 z-20">
      <div className="mx-auto flex w-full max-w-4xl items-center gap-3">
        <Button
          variant="ghost"
          size="iconSm"
          onClick={onOpenSidebar}
          aria-label="Mở menu"
          className="lg:hidden rounded-lg text-muted-foreground hover:text-foreground"
        >
          <Menu className="size-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-sm font-semibold text-foreground tracking-tight">
            {conversation?.title || "Cuộc trò chuyện mới"}
          </h1>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
            {streaming ? (
              <span className="flex items-center gap-1.5 text-brand font-medium">
                <Sparkles className="size-3 animate-spin text-brand" />
                <span>Đang xử lý phân tích...</span>
              </span>
            ) : (
              <span className="flex items-center gap-1.5 font-sans">
                <span className="size-2 rounded-full bg-emerald-500 animate-pulse-subtle" />
                <span>Trực tuyến // Sẵn sàng</span>
              </span>
            )}
          </div>
        </div>
        <Badge variant="outline" className="shrink-0 gap-1.5 rounded-full border border-brand/20 bg-brand/5 px-3 py-1 font-mono text-xs font-medium text-brand">
          <ShieldCheck className="size-3.5 text-brand" />
          <span>Derma Clinical AI</span>
        </Badge>
      </div>
    </header>
  );
}

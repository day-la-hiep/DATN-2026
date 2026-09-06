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
    <header className="border-b border-border bg-background px-4 py-3">
      <div className="mx-auto flex w-full max-w-3xl items-center gap-3">
        <Button
          variant="ghost"
          size="iconSm"
          onClick={onOpenSidebar}
          aria-label="Mở menu"
          className="lg:hidden"
        >
          <Menu className="size-5" />
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-sm font-semibold text-foreground">
            {conversation?.title || "Cuộc trò chuyện mới"}
          </h1>
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            {streaming ? (
              <>
                <Sparkles className="size-3.5 animate-pulse text-brand" />
                Đang xử lý yêu cầu của bạn...
              </>
            ) : (
              "Sẵn sàng trả lời"
            )}
          </p>
        </div>
        <Badge variant="success" className="shrink-0 gap-1">
          <ShieldCheck className="size-3.5" />
          Trợ lý AI
        </Badge>
      </div>
    </header>
  );
}

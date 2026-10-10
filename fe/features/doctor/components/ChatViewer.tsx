"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, User, Stethoscope, Info, CornerDownLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDoctorStore } from "../store";
import type { DoctorViewMessage } from "../types";
import { Hint } from "@/components/ui/hint";
import { STATUS_CONFIG } from "../constants";
import { Skeleton } from "@/components/ui/skeleton";
import { MarkdownMessage } from "@/features/chat/components/MarkdownMessage";

const SENDER_CONFIG = {
  patient: {
    label: "Bệnh nhân",
    icon: User,
    bubbleClass:
      "bg-muted/80 dark:bg-muted/50 text-foreground border border-border/50",
    iconClass:
      "bg-blue-100 dark:bg-blue-950/50 text-blue-600 dark:text-blue-400",
    align: "justify-start" as const,
  },
  ai: {
    label: "AI",
    icon: Bot,
    bubbleClass: "bg-brand/5 dark:bg-brand/10 text-foreground border border-brand/15",
    iconClass:
      "bg-brand/10 dark:bg-brand/20 text-brand",
    align: "justify-start" as const,
  },
  doctor: {
    label: "Bác sĩ",
    icon: Stethoscope,
    bubbleClass:
      "bg-emerald-50 dark:bg-emerald-950/30 text-foreground border border-emerald-200 dark:border-emerald-800/50",
    iconClass:
      "bg-emerald-100 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400",
    align: "justify-start" as const,
  },
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ChatBubble({ message }: { message: DoctorViewMessage }) {
  const cfg = SENDER_CONFIG[message.sender];
  const Icon = cfg.icon;

  const isSystemMessage =
    message.messageType === "consultation_requested" ||
    message.messageType === "consultation_accepted" ||
    message.messageType === "consultation_resolved";

  if (isSystemMessage) {
    return (
      <div className="flex justify-center py-2">
        <div className="flex items-center gap-2 rounded-full border border-border bg-muted/50 px-4 py-1.5 text-[11px] text-muted-foreground">
          <Info className="size-3" />
          <span>{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex w-full gap-2.5 py-1", cfg.align)}>
      {/* Avatar */}
      <div
        className={cn(
          "flex items-center justify-center size-7 rounded-lg shrink-0 mt-0.5",
          cfg.iconClass
        )}
      >
        <Icon className="size-3.5" />
      </div>

      {/* Bubble */}
      <div className="max-w-[85%] min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {cfg.label}
          </span>
          <span className="text-[10px] text-muted-foreground/60 font-mono">
            {formatTime(message.createdAt)}
          </span>
        </div>
        <div
          className={cn("rounded-xl rounded-tl-sm px-3.5 py-2.5", cfg.bubbleClass)}
        >
          <div className="text-[13px] leading-relaxed">
            <MarkdownMessage content={message.content} />
          </div>
        </div>
      </div>
    </div>
  );
}

export function ChatViewer() {
  const messages = useDoctorStore((s) => s.messages);
  const loadingMessages = useDoctorStore((s) => s.loadingMessages);
  const activeSessionId = useDoctorStore((s) => s.activeSessionId);
  const sessions = useDoctorStore((s) => s.sessions);
  const sendMessage = useDoctorStore((s) => s.sendMessage);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [inputText, setInputText] = useState("");

  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const isResolved = activeSession?.status === "resolved";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const handleSend = async () => {
    if (!inputText.trim() || isResolved) return;
    const text = inputText;
    setInputText("");
    await sendMessage(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!activeSessionId) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        <div className="text-center">
          <Bot className="size-10 mx-auto mb-3 opacity-30" />
          <p className="text-sm">Chọn một ca</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
        <Hint side="bottom" content={`${activeSession?.conversationTitle ?? "Cuộc hội thoại"} · ${messages.length} tin nhắn giữa AI, bệnh nhân và bác sĩ`}>
          <h3 className="min-w-0 truncate font-serif text-lg font-bold tracking-tight text-foreground">
            {activeSession?.patient?.fullName ?? activeSession?.conversationTitle ?? "Hội thoại"}
          </h3>
        </Hint>
        {activeSession && (
          <Hint side="bottom" content={STATUS_CONFIG[activeSession.status].hint}>
            <span className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <span className={cn("size-2 rounded-full", STATUS_CONFIG[activeSession.status].dotClass, activeSession.status === "active" && "animate-pulse")} />
              {STATUS_CONFIG[activeSession.status].label}
            </span>
          </Hint>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {loadingMessages ? (
          <div className="space-y-3 p-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex gap-2.5">
                <Skeleton className="size-7 rounded-lg shrink-0" />
                <div className="space-y-1.5 flex-1">
                  <Skeleton className="h-3 w-16 rounded" />
                  <Skeleton
                    className={cn(
                      "rounded-xl",
                      i % 2 === 0 ? "h-12 w-3/4" : "h-16 w-full"
                    )}
                  />
                </div>
              </div>
            ))}
          </div>
        ) : (
          messages.map((msg) => <ChatBubble key={msg.id} message={msg} />)
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-border p-3">
        {isResolved ? (
          <Hint content="Phiên tư vấn đã kết thúc, chỉ xem lại được.">
            <p className="rounded-xl bg-muted/40 p-3 text-center text-xs text-muted-foreground">Chỉ xem</p>
          </Hint>
        ) : (
          <div className="flex items-end gap-2 rounded-2xl border border-border bg-card p-2 transition-colors focus-within:border-brand/40 focus-within:ring-2 focus-within:ring-brand/10">
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Phản hồi bệnh nhân..."
              aria-label="Phản hồi bệnh nhân"
              rows={2}
              className="flex-1 resize-none bg-transparent px-2 py-1 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
            <Hint content="Gửi (Enter). Xuống dòng: Shift + Enter. Gửi tin sẽ tự nhận ca và thay AI trả lời bệnh nhân.">
              <button
                type="button"
                onClick={handleSend}
                disabled={!inputText.trim()}
                aria-label="Gửi"
                className={cn(
                  "flex size-9 shrink-0 items-center justify-center rounded-xl transition-all active:scale-95",
                  inputText.trim() ? "bg-brand text-brand-foreground shadow-sm hover:brightness-110" : "cursor-not-allowed bg-muted text-muted-foreground opacity-50"
                )}
              >
                <CornerDownLeft className="size-4" />
              </button>
            </Hint>
          </div>
        )}
      </div>
    </div>
  );
}

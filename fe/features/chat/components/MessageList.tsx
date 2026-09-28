"use client";

import { Fragment, useEffect, useRef } from "react";
import { ArrowRight, Loader2 } from "lucide-react";
import type { ChatMessage } from "../types";
import { useChatStore } from "../store";
import { MessageBubble } from "./MessageBubble";
import { ReasoningSection } from "./ReasoningSection";
import { Skeleton } from "@/components/ui/skeleton";

const SUGGESTIONS = [
  { id: "01", text: "Da mặt bị mụn trứng cá nên chăm sóc thế nào?" },
  { id: "02", text: "Phác đồ điều trị viêm da cơ địa cho trẻ em" },
  { id: "03", text: "Cách trị nám má sau sinh an toàn và hiệu quả" },
  { id: "04", text: "Nấm da chân tái đi tái lại nhiều lần" },
];

export function MessageList({
  conversationId,
  messages,
  loading,
}: {
  conversationId: string;
  messages: ChatMessage[];
  loading: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const streaming = useChatStore((s) => s.hasActiveStream(conversationId));

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streaming]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <div className="flex flex-col gap-3 w-full max-w-xl">
          <Skeleton className="h-6 w-1/3 rounded-xl" />
          <Skeleton className="h-20 w-full rounded-2xl" />
          <Skeleton className="h-16 w-3/4 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="relative mx-auto flex w-full max-w-4xl flex-1 flex-col justify-center px-4 py-8 sm:px-8">
        {/* Ambient background glow */}
        <div className="ambient-glow size-96 -top-10 left-1/2 -translate-x-1/2" />

        {/* Hero Card */}
        <div className="relative rounded-3xl border border-border bg-card/60 backdrop-blur-sm p-6 sm:p-10 shadow-sm modern-dot-pattern">
          {/* Section Indicator Badge */}
          <div className="flex items-center justify-between pb-6">
            <div className="inline-flex items-center gap-2.5 rounded-full border border-brand/25 bg-brand/5 px-4 py-1.5 shadow-xs">
              <span className="size-2 rounded-full bg-brand animate-pulse-subtle" />
              <span className="font-mono text-xs uppercase tracking-[0.15em] text-brand font-medium">
                Clinical Intelligence
              </span>
            </div>
            <span className="font-mono text-xs text-muted-foreground">
              v2.4 Pro
            </span>
          </div>

          <div className="flex flex-col gap-3">
            <h1 className="text-3xl sm:text-5xl lg:text-6xl font-serif font-normal tracking-tight text-foreground leading-[1.1]">
              Hỏi đáp cùng <span className="gradient-text">Trợ lý Da liễu AI</span>
            </h1>
            <p className="max-w-xl text-sm sm:text-base text-muted-foreground leading-relaxed pt-2">
              Hệ thống tra cứu, hỗ trợ phân loại tổn thương và định hướng chăm sóc da dựa trên y văn chuyên môn. Đặt câu hỏi trực tiếp hoặc tham khảo các trường hợp thường gặp:
            </p>
          </div>

          {/* Suggestions Grid */}
          <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-3.5 pt-4">
            {SUGGESTIONS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => sendMessage(item.text)}
                className="group relative flex flex-col justify-between rounded-2xl border border-border bg-card/90 p-5 text-left transition-all duration-200 hover:shadow-md hover:border-brand/40 hover:-translate-y-0.5 cursor-pointer"
              >
                <div className="flex items-center justify-between w-full mb-3">
                  <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded-md bg-brand/10 text-brand">
                    {item.id}
                  </span>
                  <ArrowRight className="size-4 text-muted-foreground transition-transform duration-200 group-hover:translate-x-1 group-hover:text-brand" />
                </div>
                <span className="text-sm font-medium text-foreground group-hover:text-brand transition-colors line-clamp-2">
                  {item.text}
                </span>
              </button>
            ))}
          </div>

          {/* Bottom disclaimer */}
          <div className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-border/60 pt-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-brand" />
              <span>Chẩn đoán và dữ liệu tham khảo theo phác đồ da liễu</span>
            </div>
            <span className="font-mono text-[10px] text-muted-foreground/70">
              Dual-Font: Calistoga + Inter
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-6 sm:px-8">
      {messages.map((message) => {
        if (message.role === "user") {
          return <MessageBubble key={message.id} message={message} />;
        }

        const hasReasoning = (message.reasoning?.length ?? 0) > 0;
        const hasContent = message.content.trim().length > 0;
        return (
          <Fragment key={message.id}>
            {hasReasoning && (
              <ReasoningSection
                steps={message.reasoning!}
                messageId={message.id}
                streaming={message.status === "streaming"}
              />
            )}
            {hasContent && <MessageBubble message={message} />}
          </Fragment>
        );
      })}

      {streaming &&
        !messages.some(
          (m) => m.status === "streaming" && (m.reasoning?.length ?? 0) > 0
        ) && (
          <div className="flex justify-start animate-in fade-in-0 duration-200">
            <div className="flex items-center gap-2.5 rounded-full border border-brand/25 bg-brand/5 px-4 py-2 font-mono text-xs text-brand shadow-xs">
              <Loader2 className="size-3.5 animate-spin text-brand" />
              <span>AI đang truy vấn và suy luận chẩn đoán...</span>
            </div>
          </div>
        )}
      <div ref={bottomRef} />
    </div>
  );
}

"use client";

import { Fragment, useEffect, useRef } from "react";
import { Stethoscope, Sparkles } from "lucide-react";
import type { ChatMessage } from "../types";
import { useChatStore } from "../store";
import { MessageBubble } from "./MessageBubble";
import { ReasoningSection } from "./ReasoningSection";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const SUGGESTIONS = [
  "Da mặt bị mụn trứng cá nên chăm sóc thế nào?",
  "Phác đồ điều trị viêm da cơ địa cho trẻ",
  "Cách trị nám má sau sinh an toàn",
  "Nấm da chân tái đi tái lại phải làm sao?",
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
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-20 w-full rounded-2xl" />
          <Skeleton className="h-16 w-3/4 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-8 px-4 py-6 sm:px-6">
        <Card className="w-full items-center text-center border-none shadow-none bg-transparent gap-3 py-0">
          <CardHeader className="items-center p-0 gap-3">
            <div className="flex size-16 items-center justify-center rounded-2xl bg-brand/10 text-brand">
              <Stethoscope className="size-8" />
            </div>
            <CardTitle className="text-xl font-semibold text-foreground">
              Trợ lý da liễu AI
            </CardTitle>
            <CardDescription className="max-w-md text-sm text-muted-foreground">
              Hỏi tôi về các bệnh lý da, cách chăm sóc da, hướng dẫn dùng thuốc...
              Tôi sẽ tra cứu và tư vấn theo hướng dẫn chuyên môn da liễu.
            </CardDescription>
          </CardHeader>
        </Card>

        <div className="grid w-full max-w-lg grid-cols-1 gap-2 sm:grid-cols-2">
          {SUGGESTIONS.map((suggestion) => (
            <Button
              key={suggestion}
              variant="outline"
              onClick={() => sendMessage(suggestion)}
              className="h-auto whitespace-normal rounded-xl border-border bg-background px-4 py-3 text-left text-sm text-muted-foreground font-normal transition-colors hover:border-brand/40 hover:bg-brand/5 hover:text-foreground justify-start"
            >
              {suggestion}
            </Button>
          ))}
        </div>

        <Badge variant="outline" className="gap-1.5 py-1 px-3 text-xs font-normal text-muted-foreground border-border">
          <Sparkles className="size-3.5 text-brand" />
          <span>Đang chạy chế độ demo với dữ liệu mô phỏng</span>
        </Badge>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-4 py-6 sm:px-6">
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
      {streaming && (
        <div className="flex justify-start">
          <Card className="flex flex-row items-center gap-1.5 rounded-2xl rounded-bl-md border-border bg-card px-4 py-3 shadow-none">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="size-2 animate-bounce rounded-full bg-muted-foreground/50"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </Card>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

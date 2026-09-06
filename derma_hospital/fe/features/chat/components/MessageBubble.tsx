"use client";

import { useRef } from "react";
import { Check, FileText, Sparkles } from "lucide-react";
import type { ChatMessage } from "../types";
import { MarkdownMessage } from "./MarkdownMessage";
import { SelectionAsk } from "./SelectionAsk";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

interface QAPair {
  question: string;
  answer: string;
}

function parseQAPairs(content: string): QAPair[] {
  const pairs: QAPair[] = [];
  const lines = content.split("\n");
  let currentQuestion = "";
  let currentAnswer = "";

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("[Câu hỏi]")) {
      if (currentQuestion && currentAnswer) {
        pairs.push({ question: currentQuestion, answer: currentAnswer });
        currentAnswer = "";
      }
      currentQuestion = trimmed.replace("[Câu hỏi]", "").trim();
    } else if (trimmed.startsWith("[Trả lời]")) {
      currentAnswer = trimmed.replace("[Trả lời]", "").trim();
    }
  }

  if (currentQuestion && currentAnswer) {
    pairs.push({ question: currentQuestion, answer: currentAnswer });
  }

  return pairs;
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const streaming = message.status === "streaming";
  const contentRef = useRef<HTMLDivElement>(null);

  if (isUser) {
    const isChoiceAnswerMessage =
      message.content.includes("[Câu hỏi]") && message.content.includes("[Trả lời]");

    // Format đơn giản cho tin nhắn Lựa chọn phương án: Tràn 2 bên (w-full), không separator, hỗ trợ nhiều câu hỏi trong 1 lượt
    if (isChoiceAnswerMessage) {
      const qaPairs = parseQAPairs(message.content);

      return (
        <div id={`msg-${message.id}`} className="flex w-full py-1">
          <Card
            ref={contentRef}
            className="w-full rounded-2xl border border-border bg-card p-3.5 sm:p-4 text-foreground shadow-xs"
          >
            <div className="flex flex-col gap-2">
              {qaPairs.map((pair, index) => (
                <div key={index} className="flex items-start gap-2 text-xs sm:text-sm">
                  <Check className="size-4 text-brand shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0 text-justify leading-relaxed">
                    {pair.question && (
                      <span className="text-muted-foreground font-normal mr-1.5">
                        {pair.question}:
                      </span>
                    )}
                    <span className="font-semibold text-foreground">{pair.answer}</span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      );
    }

    // Tin nhắn User thông thường (căn phải)
    return (
      <div
        id={`msg-${message.id}`}
        className="flex w-full justify-end"
      >
        <SelectionAsk
          messageId={message.id}
          containerRef={contentRef}
          className="flex justify-end max-w-[85%] sm:max-w-[75%]"
        >
          <div
            ref={contentRef}
            className="w-full rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-sm leading-relaxed text-brand-foreground"
          >
            {(() => {
              const refs = Array.isArray(message.selectionRef)
                ? message.selectionRef
                : message.selectionRef
                ? [message.selectionRef]
                : [];
              if (refs.length === 0) return null;
              return (
                <div className="mb-1.5 flex flex-col gap-1">
                  {refs.map((ref, idx) => (
                    <Alert
                      key={`${ref.source}-${ref.refId}-${idx}`}
                      className="border-l-2 border-brand-foreground/60 border-y-0 border-r-0 bg-transparent p-0 pl-2.5 text-brand-foreground shadow-none"
                    >
                      <AlertTitle className="text-[11px] font-medium text-brand-foreground/75">
                        {ref.source === "canvas"
                          ? "Trích từ canvas"
                          : ref.source === "document"
                          ? "Trích từ tài liệu"
                          : "Trích từ tin nhắn"}{" "}
                        {refs.length > 1 ? `#${idx + 1}` : ""}
                      </AlertTitle>
                      <AlertDescription className="mt-0.5 line-clamp-3 text-xs whitespace-pre-wrap opacity-90 text-brand-foreground">
                        “{ref.text}”
                      </AlertDescription>
                    </Alert>
                  ))}
                </div>
              );
            })()}
            {message.attachments && message.attachments.length > 0 && (
              <div className="mb-1.5 flex flex-wrap gap-1.5">
                {message.attachments.map((file) => (
                  <Badge
                    key={file.id}
                    variant="secondary"
                    className="flex items-center gap-1 bg-brand-foreground/15 text-xs text-brand-foreground hover:bg-brand-foreground/20"
                  >
                    <FileText className="size-3" />
                    <span>{file.name}</span>
                  </Badge>
                ))}
              </div>
            )}
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
        </SelectionAsk>
      </div>
    );
  }

  // Assistant message: Chỉ hiển thị nội dung câu hỏi/tin nhắn (không render lại ChoiceBlock bên dưới tin nhắn)
  return (
    <div
      id={`msg-${message.id}`}
      className="flex w-full justify-start py-1.5 text-foreground"
    >
      <SelectionAsk
        messageId={message.id}
        containerRef={contentRef}
        className="w-full"
      >
        <div className="w-full max-w-full text-sm leading-relaxed">
          {message.content ? (
            <div ref={contentRef} className="flex items-start gap-1">
              <div className="min-w-0 flex-1">
                <MarkdownMessage content={message.content} />
              </div>
              {streaming && (
                <span className="mt-1 inline-block h-4 w-0.5 animate-pulse rounded bg-brand shrink-0" />
              )}
            </div>
          ) : (
            <Badge variant="outline" className="gap-1.5 py-1 px-2.5 text-xs font-medium text-muted-foreground border-border bg-card">
              <Sparkles className="size-4 animate-pulse text-brand" />
              <span>AI đang suy nghĩ và tổng hợp thông tin...</span>
            </Badge>
          )}
        </div>
      </SelectionAsk>
    </div>
  );
}

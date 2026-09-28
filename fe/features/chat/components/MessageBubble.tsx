"use client";

import { useRef } from "react";
import { FileText, Sparkles } from "lucide-react";
import type { ChatMessage } from "../types";
import { ImageThumbnail } from "./ImageThumbnail";
import { MarkdownMessage } from "./MarkdownMessage";
import { SelectionAsk } from "./SelectionAsk";

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

    // Format cho tin nhắn Trả lời lựa chọn phương án
    if (isChoiceAnswerMessage) {
      const qaPairs = parseQAPairs(message.content);

      return (
        <div id={`msg-${message.id}`} className="flex w-full justify-end py-1">
          <div
            ref={contentRef}
            className="w-auto max-w-[90%] sm:max-w-[80%] rounded-2xl rounded-tr-xs bg-brand text-white p-4 shadow-sm shadow-brand/20"
          >
            <div className="flex flex-col gap-2">
              {qaPairs.map((pair, index) => (
                <div key={index} className="flex items-start gap-2 text-xs sm:text-sm">
                  <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded-md bg-white/20 text-white shrink-0">
                    Q{index + 1}
                  </span>
                  <div className="flex-1 min-w-0 leading-relaxed">
                    {pair.question && (
                      <span className="text-white/80 mr-1.5">
                        {pair.question}:
                      </span>
                    )}
                    <span className="font-medium text-white">
                      {pair.answer}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    // Tin nhắn User thông thường: đơn giản, ưu tiên core color
    return (
      <div
        id={`msg-${message.id}`}
        className="flex w-full justify-end py-1"
      >
        <SelectionAsk
          messageId={message.id}
          containerRef={contentRef}
          className="flex justify-end max-w-[90%] sm:max-w-[75%]"
        >
          <div
            ref={contentRef}
            className="w-full rounded-2xl rounded-tr-xs bg-brand text-white px-4 py-3 sm:px-5 sm:py-3.5 shadow-sm shadow-brand/20 leading-relaxed"
          >
            {/* Trích dẫn selection */}
            {(() => {
              const refs = Array.isArray(message.selectionRef)
                ? message.selectionRef
                : message.selectionRef
                ? [message.selectionRef]
                : [];
              if (refs.length === 0) return null;
              return (
                <div className="mb-2.5 flex flex-col gap-1.5">
                  {refs.map((ref, idx) => (
                    <div
                      key={`${ref.source}-${ref.refId}-${idx}`}
                      className="rounded-xl border-l-2 border-white/60 bg-white/10 p-2.5 text-white text-xs"
                    >
                      <span className="block text-[10px] font-mono uppercase tracking-wider text-white/80 font-semibold">
                        Trích dẫn {refs.length > 1 ? `#${idx + 1}` : ""}:
                      </span>
                      <p className="mt-0.5 whitespace-pre-wrap text-white/95 line-clamp-3">
                        “{ref.text}”
                      </p>
                    </div>
                  ))}
                </div>
              );
            })()}

            {/* File đính kèm */}
            {message.attachments && message.attachments.length > 0 && (
              <div className="mb-2.5 flex flex-wrap gap-2">
                {message.attachments.map((file) => {
                  const isPreviewableImage = file.type?.startsWith("image/") && file.url;
                  return isPreviewableImage ? (
                    <div key={file.id} className="rounded-xl overflow-hidden border border-white/20">
                      <ImageThumbnail
                        url={file.url!}
                        name={file.name}
                        size={64}
                        fileSize={file.size}
                      />
                    </div>
                  ) : (
                    <div
                      key={file.id}
                      className="flex items-center gap-1.5 rounded-lg border border-white/20 bg-white/10 px-2.5 py-1.5 text-xs text-white"
                    >
                      <FileText className="size-3.5" />
                      <span>{file.name}</span>
                    </div>
                  );
                })}
              </div>
            )}

            <p className="whitespace-pre-wrap text-sm sm:text-base font-normal text-white">{message.content}</p>
          </div>
        </SelectionAsk>
      </div>
    );
  }

  // Assistant message: không đóng khung, render trực tiếp markdown
  return (
    <div
      id={`msg-${message.id}`}
      className="flex w-full justify-start py-1 text-foreground"
    >
      <SelectionAsk
        messageId={message.id}
        containerRef={contentRef}
        className="w-full"
      >
        <div ref={contentRef} className="w-full text-foreground">
          {message.content ? (
            <div className="text-sm sm:text-base leading-relaxed text-foreground">
              <MarkdownMessage content={message.content} />
              {streaming && (
                <span className="inline-block size-2 rounded-full bg-brand ml-1.5 animate-pulse" />
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2.5 py-3 text-sm text-muted-foreground">
              <Sparkles className="size-4 animate-spin text-brand" />
              <span>Đang suy nghĩ câu trả lời...</span>
            </div>
          )}
        </div>
      </SelectionAsk>
    </div>
  );
}

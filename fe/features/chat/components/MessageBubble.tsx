"use client";

import { FileText, Sparkles, Stethoscope } from "lucide-react";
import type { ChatMessage } from "../types";
import { ImageThumbnail } from "./ImageThumbnail";
import { MarkdownMessage } from "./MarkdownMessage";

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
  const isDoctor = message.role === "doctor";
  const streaming = message.status === "streaming";

  if (isDoctor) {
    return (
      <div
        id={`msg-${message.id}`}
        className="flex w-full justify-start py-2 text-foreground"
      >
        <div className="w-full max-w-[90%] sm:max-w-[80%] rounded-2xl rounded-tl-xs border border-sky-500/30 bg-sky-50/60 dark:bg-sky-950/20 p-4 shadow-sm shadow-sky-500/5">
          <div className="flex items-center gap-2 mb-2 pb-2 border-b border-sky-500/15">
            <span className="flex size-6 items-center justify-center rounded-full bg-sky-500 text-white shadow-xs">
              <Stethoscope className="size-3.5" />
            </span>
            <span className="text-xs font-semibold text-sky-800 dark:text-sky-300">
              Bác sĩ chuyên khoa phụ trách
            </span>
            <span className="ml-auto font-mono text-[10px] text-muted-foreground">
              {new Date(message.createdAt).toLocaleTimeString("vi-VN", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
          <div className="text-sm sm:text-base leading-relaxed text-foreground">
            <MarkdownMessage content={message.content} />
          </div>
        </div>
      </div>
    );
  }

  if (isUser) {
    const isChoiceAnswerMessage =
      message.content.includes("[Câu hỏi]") && message.content.includes("[Trả lời]");

    // Format cho tin nhắn Trả lời lựa chọn phương án
    if (isChoiceAnswerMessage) {
      const qaPairs = parseQAPairs(message.content);

      return (
        <div id={`msg-${message.id}`} className="flex w-full justify-end py-1">
          <div
            className="w-auto max-w-[90%] sm:max-w-[80%] rounded-2xl rounded-tr-xs bg-brand text-brand-foreground p-4 shadow-sm shadow-brand/20"
          >
            <div className="flex flex-col gap-2">
              {qaPairs.map((pair, index) => (
                <div key={index} className="flex items-start gap-2 text-xs sm:text-sm">
                  <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded-md bg-brand-foreground/15 text-brand-foreground shrink-0">
                    Q{index + 1}
                  </span>
                  <div className="flex-1 min-w-0 leading-relaxed">
                    {pair.question && (
                      <span className="text-brand-foreground/80 mr-1.5">
                        {pair.question}:
                      </span>
                    )}
                    <span className="font-medium text-brand-foreground">
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
        <div className="relative flex justify-end max-w-[90%] sm:max-w-[75%]">
          <div
            className="w-full rounded-2xl rounded-tr-xs bg-brand text-brand-foreground px-4 py-3 sm:px-5 sm:py-3.5 shadow-sm shadow-brand/20 leading-relaxed"
          >
            {/* File đính kèm */}
            {message.attachments && message.attachments.length > 0 && (
              <div className="mb-2.5 flex flex-wrap gap-2">
                {message.attachments.map((file) => {
                  const isPreviewableImage = file.type?.startsWith("image/") && file.url;
                  return isPreviewableImage ? (
                    <div key={file.id} className="rounded-xl overflow-hidden border border-brand-foreground/20">
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
                      className="flex items-center gap-1.5 rounded-lg border border-brand-foreground/20 bg-brand-foreground/10 px-2.5 py-1.5 text-xs text-brand-foreground"
                    >
                      <FileText className="size-3.5" />
                      <span>{file.name}</span>
                    </div>
                  );
                })}
              </div>
            )}

            <p className="whitespace-pre-wrap text-sm sm:text-base font-normal text-brand-foreground">{message.content}</p>
          </div>
        </div>
      </div>
    );
  }

  // Assistant message: không đóng khung, render trực tiếp markdown
  return (
    <div
      id={`msg-${message.id}`}
      className="flex w-full justify-start py-1 text-foreground"
    >
      <div className="relative w-full">
        <div className="w-full text-foreground">
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
      </div>
    </div>
  );
}

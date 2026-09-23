"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Send,
  Sparkles,
  SkipForward,
  X,
} from "lucide-react";
import type { ChoiceOption } from "../types";
import { useChatStore } from "../store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface QuestionModalProps {
  conversationId: string;
}

export function QuestionModal({ conversationId }: QuestionModalProps) {
  const messagesByConversation = useChatStore((s) => s.messagesByConversation);
  const answerChoice = useChatStore((s) => s.answerChoice);

  const unansweredMessages = useMemo(() => {
    const list = messagesByConversation[conversationId] ?? [];
    return list.filter(
      (m) => m.role === "assistant" && m.choice && !m.choice.answered
    );
  }, [messagesByConversation, conversationId]);

  const [currentIndex, setCurrentIndex] = useState(0);
  const [customText, setCustomText] = useState("");
  const [minimizedId, setMinimizedId] = useState<string | null>(null);

  const modalRef = useRef<HTMLDivElement>(null);

  const safeIndex = Math.min(
    currentIndex,
    Math.max(0, unansweredMessages.length - 1)
  );

  const targetMessage = unansweredMessages[safeIndex];
  const choice = targetMessage?.choice;
  const isMinimized = targetMessage ? minimizedId === targetMessage.id : false;

  useEffect(() => {
    if (!targetMessage) return;
    const currentId = targetMessage.id;

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (modalRef.current && !modalRef.current.contains(target)) {
        setMinimizedId(currentId);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [targetMessage]);

  const handlePrev = useCallback(() => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
    setCustomText("");
  }, []);

  const handleNext = useCallback(() => {
    setCurrentIndex((prev) => Math.min(unansweredMessages.length - 1, prev + 1));
    setCustomText("");
  }, [unansweredMessages.length]);

  useEffect(() => {
    if (!targetMessage) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        document.activeElement?.tagName === "INPUT" ||
        document.activeElement?.tagName === "TEXTAREA"
      ) {
        return;
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        handlePrev();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        handleNext();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [targetMessage, handlePrev, handleNext]);

  if (!targetMessage || !choice) return null;

  const handleSelectOption = (option: ChoiceOption) => {
    answerChoice(targetMessage.id, {
      optionId: option.id,
      label: option.label,
      custom: false,
    });
    setCustomText("");
  };

  const handleSubmitCustom = () => {
    if (!customText.trim()) return;
    answerChoice(targetMessage.id, {
      optionId: "custom",
      label: customText.trim(),
      custom: true,
    });
    setCustomText("");
  };

  const handleSkip = () => {
    answerChoice(targetMessage.id, {
      optionId: "skip",
      label: "Bỏ qua câu hỏi này",
      custom: true,
    });
    setCustomText("");
  };

  if (isMinimized) {
    return (
      <div className="absolute bottom-full left-0 right-0 z-40 mb-3 flex justify-center px-4">
        <button
          type="button"
          onClick={() => setMinimizedId(null)}
          className="flex items-center gap-2 rounded-full border border-brand/30 bg-card/90 backdrop-blur-md text-foreground px-4 py-2 text-xs font-medium shadow-lg hover:shadow-accent hover:-translate-y-0.5 transition-all cursor-pointer"
        >
          <Sparkles className="size-3.5 text-brand animate-spin" />
          <span>Có câu hỏi làm rõ từ AI ({unansweredMessages.length})</span>
          <span className="bg-brand text-white text-[10px] font-semibold px-2 py-0.5 rounded-full">Xem</span>
        </button>
      </div>
    );
  }

  return (
    <div className="absolute bottom-full left-0 right-0 z-40 mb-3 flex justify-center px-4 animate-in fade-in-0 duration-200">
      <div
        ref={modalRef}
        className="w-full max-w-md rounded-2xl border border-border bg-card/95 backdrop-blur-md p-5 shadow-xl text-foreground"
      >
        {/* Top: Section indicator + Pagination + Close */}
        <div className="flex items-center justify-between pb-3 mb-3 border-b border-border/60">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-brand animate-pulse-subtle" />
            <span className="font-mono text-xs uppercase tracking-wider text-brand font-medium">
              Câu hỏi làm rõ
            </span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0 font-mono text-xs">
            {unansweredMessages.length > 1 && (
              <div className="flex items-center gap-1 pr-1.5 border-r border-border mr-1">
                <button
                  type="button"
                  onClick={handlePrev}
                  disabled={safeIndex === 0}
                  className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-30 cursor-pointer"
                  aria-label="Câu trước"
                >
                  <ChevronLeft className="size-3.5" />
                </button>
                <span className="font-medium text-xs text-muted-foreground">
                  {safeIndex + 1}/{unansweredMessages.length}
                </span>
                <button
                  type="button"
                  onClick={handleNext}
                  disabled={safeIndex === unansweredMessages.length - 1}
                  className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-30 cursor-pointer"
                  aria-label="Câu tiếp"
                >
                  <ChevronRight className="size-3.5" />
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={() => setMinimizedId(targetMessage.id)}
              aria-label="Thu gọn"
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer"
            >
              <X className="size-4" />
            </button>
          </div>
        </div>

        {/* Tiêu đề câu hỏi */}
        <p className="text-sm font-semibold text-foreground mb-3 leading-snug">
          {choice.question}
        </p>

        {/* Danh sách các lựa chọn */}
        <div className="flex max-h-48 flex-col gap-2 overflow-y-auto pr-0.5 mb-3.5">
          {choice.options.map((option, idx) => (
            <button
              key={option.id}
              type="button"
              onClick={() => handleSelectOption(option)}
              className="flex items-center justify-between border border-border bg-card/60 p-2.5 text-left text-xs font-medium transition-all hover:border-brand/40 hover:bg-brand/5 hover:text-brand rounded-xl cursor-pointer"
            >
              <span className="flex items-center gap-2.5">
                <span className="font-mono text-[10px] text-muted-foreground">[{String(idx + 1).padStart(2, "0")}]</span>
                <span>{option.label}</span>
              </span>
              <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
            </button>
          ))}
        </div>

        {/* Bottom row: Nhập ý kiến + Gửi + Bỏ qua */}
        <div className="flex items-center gap-2 border-t border-border/60 pt-3">
          <div className="flex flex-1 items-center gap-2">
            <Input
              type="text"
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSubmitCustom();
              }}
              placeholder="Ý kiến khác (tự nhập)..."
              className="h-9 flex-1 text-xs rounded-xl"
            />
            <Button
              size="sm"
              onClick={handleSubmitCustom}
              disabled={!customText.trim()}
              className="h-9 px-3.5 text-xs font-medium rounded-xl shrink-0"
            >
              <Send className="size-3.5 mr-1" />
              <span>Gửi</span>
            </Button>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleSkip}
            className="h-9 px-2.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground shrink-0 rounded-xl"
          >
            <SkipForward className="size-3.5 mr-1" />
            <span>Bỏ qua</span>
          </Button>
        </div>
      </div>
    </div>
  );
}

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
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

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
  const [isMinimized, setIsMinimized] = useState(false);

  const modalRef = useRef<HTMLDivElement>(null);

  const safeIndex = Math.min(
    currentIndex,
    Math.max(0, unansweredMessages.length - 1)
  );

  const targetMessage = unansweredMessages[safeIndex];
  const choice = targetMessage?.choice;

  useEffect(() => {
    if (!targetMessage) return;
    setIsMinimized(false);

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (modalRef.current && !modalRef.current.contains(target)) {
        setIsMinimized(true);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [targetMessage?.id]);

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
      <div className="absolute bottom-full left-0 right-0 z-40 mb-2 flex justify-center px-4">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setIsMinimized(false)}
          className="group flex items-center gap-2 rounded-full border-brand/40 bg-popover px-3 py-1 text-xs font-semibold text-popover-foreground shadow-lg transition-all hover:border-brand hover:bg-brand/10 hover:text-brand cursor-pointer"
        >
          <Sparkles className="size-3.5 animate-pulse text-brand" />
          <span>Có câu hỏi từ AI ({unansweredMessages.length})</span>
          <Badge variant="default" className="ml-0.5 text-[10px] px-1.5 py-0">
            Mở
          </Badge>
        </Button>
      </div>
    );
  }

  return (
    <div className="absolute bottom-full left-0 right-0 z-40 mb-2 flex justify-center px-4 animate-in fade-in-0 slide-in-from-bottom-2 duration-200">
      <Card
        ref={modalRef}
        className="w-full max-w-sm gap-2.5 p-3 shadow-xl backdrop-blur-none border-border bg-popover text-popover-foreground rounded-2xl"
      >
        {/* Top: Tiêu đề câu hỏi + Điều hướng & Nút thu gọn */}
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs sm:text-sm font-semibold text-foreground leading-snug flex-1">
            {choice.question}
          </p>

          <div className="flex items-center gap-0.5 shrink-0">
            {unansweredMessages.length > 1 && (
              <div className="flex items-center gap-0.5 pr-1">
                <Button
                  variant="ghost"
                  size="iconSm"
                  onClick={handlePrev}
                  disabled={safeIndex === 0}
                  aria-label="Câu trước"
                  className="size-6 text-muted-foreground"
                >
                  <ChevronLeft className="size-3" />
                </Button>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {safeIndex + 1}/{unansweredMessages.length}
                </span>
                <Button
                  variant="ghost"
                  size="iconSm"
                  onClick={handleNext}
                  disabled={safeIndex === unansweredMessages.length - 1}
                  aria-label="Câu tiếp"
                  className="size-6 text-muted-foreground"
                >
                  <ChevronRight className="size-3" />
                </Button>
              </div>
            )}

            <Button
              variant="ghost"
              size="iconSm"
              onClick={() => setIsMinimized(true)}
              aria-label="Thu gọn"
              className="size-6 text-muted-foreground hover:text-foreground"
            >
              <X className="size-3" />
            </Button>
          </div>
        </div>

        {/* Danh sách các lựa chọn */}
        <div className="flex max-h-40 flex-col gap-1 overflow-y-auto pr-0.5">
          {choice.options.map((option) => (
            <Button
              key={option.id}
              variant="outline"
              onClick={() => handleSelectOption(option)}
              className="h-auto w-full justify-between whitespace-normal rounded-lg border-border bg-background px-2.5 py-1.5 text-left text-xs font-medium text-foreground transition-all hover:border-brand/50 hover:bg-brand/5 hover:text-brand"
            >
              <span>{option.label}</span>
              <ChevronRight className="size-3 shrink-0 text-muted-foreground/50 group-hover:text-brand" />
            </Button>
          ))}
        </div>

        {/* Bottom row: Ô tự nhập ý kiến + Gửi + Bỏ qua */}
        <div className="flex items-center gap-1.5 border-t border-border/60 pt-2">
          <div className="flex flex-1 items-center gap-1">
            <Input
              type="text"
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSubmitCustom();
              }}
              placeholder="Ý kiến khác (Tự nhập)..."
              className="h-7 flex-1 text-xs px-2"
            />
            <Button
              size="sm"
              onClick={handleSubmitCustom}
              disabled={!customText.trim()}
              className="h-7 px-2 text-[11px] gap-1 shrink-0"
            >
              <Send className="size-3" />
              <span>Gửi</span>
            </Button>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleSkip}
            className="h-7 px-1.5 text-[11px] gap-1 text-muted-foreground hover:bg-accent hover:text-foreground shrink-0"
          >
            <SkipForward className="size-3" />
            <span>Bỏ qua</span>
          </Button>
        </div>
      </Card>
    </div>
  );
}

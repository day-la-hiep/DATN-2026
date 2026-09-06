"use client";

import { useState } from "react";
import { Brain, Check, CheckCircle2, ChevronDown, HelpCircle, Loader2, Sparkles, Wrench } from "lucide-react";
import type { ReasoningStep, ChoiceOption } from "../types";
import { useChatStore } from "../store";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

function StepItem({
  step,
  messageId,
}: {
  step: ReasoningStep;
  messageId?: string;
  isLast?: boolean;
}) {
  const isToolCall = step.type === "tool_call" || step.type === "tool_ask" || !!step.choice;
  const hasChoice = !!step.choice;
  const isAnswered = !!step.choice?.answered;
  const [open, setOpen] = useState(isToolCall && !isAnswered);
  const processing = step.status === "processing";

  const handleSelectOption = (option: ChoiceOption) => {
    if (!messageId || !step.choice) return;
    useChatStore.getState().answerChoice(messageId, {
      optionId: option.id,
      label: option.label,
    });
  };

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="relative flex items-start gap-2 text-left">
      {/* Icon node */}
      <div className="relative z-10 flex size-3.5 shrink-0 items-center justify-center rounded-full border border-border bg-background shadow-xs mt-0.5">
        {isToolCall ? (
          <Wrench className="size-2.5 text-brand" />
        ) : processing ? (
          <Loader2 className="size-2.5 animate-spin text-brand" />
        ) : (
          <Check className="size-2 text-brand" />
        )}
      </div>

      {/* Tiêu đề & Nội dung */}
      <div className="min-w-0 flex-1">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="group flex w-full items-center justify-between gap-2 text-left transition-colors cursor-pointer"
          >
            <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
              <span
                className={cn(
                  "text-xs transition-colors hover:text-foreground",
                  open || isToolCall ? "font-medium text-foreground" : "text-muted-foreground"
                )}
              >
                {step.title}
              </span>
              {isToolCall && (
                <Badge variant="outline" className="border-brand/40 bg-brand/10 text-[9px] text-brand py-0 px-1 font-mono uppercase tracking-wider flex items-center gap-1">
                  <Wrench className="size-2" />
                  Tool Call
                </Badge>
              )}
              {hasChoice && isAnswered && (
                <Badge variant="outline" className="border-brand/40 bg-brand/10 text-[10px] text-brand py-0 px-1.5 font-medium flex items-center gap-1">
                  <CheckCircle2 className="size-3 text-brand" />
                  {step.choice?.answered?.label}
                </Badge>
              )}
            </div>
            <ChevronDown
              className={cn(
                "size-3 shrink-0 text-muted-foreground/50 transition-transform group-hover:text-foreground",
                open && "rotate-180"
              )}
            />
          </button>
        </CollapsibleTrigger>

        <CollapsibleContent className="mt-1 animate-in fade-in-0 duration-150">
          <div className="text-xs leading-relaxed text-muted-foreground space-y-2 py-1">
            {step.content && <p className="whitespace-pre-wrap">{step.content}</p>}
            {processing && <span className="animate-pulse">▍</span>}

            {/* Render đặc biệt cho Tool Call lấy phương án người dùng */}
            {hasChoice && (
              <div className="mt-2.5 space-y-2.5 border-t border-border/40 pt-2.5">
                <p className="font-medium text-foreground text-xs flex items-center gap-1.5">
                  <HelpCircle className="size-3.5 text-brand shrink-0" />
                  {step.choice?.question}
                </p>

                {/* Khi đã trả lời: Render banner xác nhận lựa chọn nổi bật */}
                {isAnswered && (
                  <div className="flex items-center justify-between rounded-lg border border-brand/30 bg-brand/10 px-3 py-2 text-xs shadow-2xs">
                    <div className="flex items-center gap-2 text-foreground font-medium min-w-0">
                      <CheckCircle2 className="size-4 text-brand shrink-0" />
                      <span className="truncate">Lựa chọn đã chọn: <strong className="text-brand font-semibold">{step.choice?.answered?.label}</strong></span>
                    </div>
                    <Badge variant="outline" className="border-brand/30 bg-brand/20 text-brand text-[10px] py-0 px-2 shrink-0 font-medium">
                      Đã xác nhận
                    </Badge>
                  </div>
                )}

                {/* Danh sách các phương án */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 pt-1">
                  {step.choice?.options.map((opt) => {
                    const isSelected =
                      step.choice?.answered?.optionId === opt.id ||
                      step.choice?.answered?.label === opt.label;

                    if (isAnswered) {
                      return (
                        <div
                          key={opt.id}
                          className={cn(
                            "flex items-center gap-2 rounded-lg border py-1.5 px-2.5 text-xs transition-all",
                            isSelected
                              ? "border-brand/50 bg-brand/10 text-foreground font-medium shadow-2xs"
                              : "border-border/40 bg-muted/20 text-muted-foreground/60"
                          )}
                        >
                          {isSelected ? (
                            <Check className="size-3.5 text-brand shrink-0" />
                          ) : (
                            <span className="size-3.5 shrink-0" />
                          )}
                          <span className="truncate">{opt.label}</span>
                        </div>
                      );
                    }

                    return (
                      <Button
                        key={opt.id}
                        variant="outline"
                        size="sm"
                        onClick={() => handleSelectOption(opt)}
                        className="h-auto py-1.5 px-2.5 text-left text-xs whitespace-normal justify-start border-border bg-background hover:bg-brand/10 hover:border-brand/30 hover:text-brand transition-all cursor-pointer"
                      >
                        {opt.label}
                      </Button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

export function ReasoningSection({
  steps,
  messageId,
  streaming,
}: {
  steps: ReasoningStep[];
  messageId?: string;
  streaming: boolean;
}) {
  const [open, setOpen] = useState(true);
  const processingCount = steps.filter(
    (step) => step.status === "processing"
  ).length;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="my-1.5 w-full text-left">
      {/* Căn trái + Nhỏ gọn tối giản */}
      <div className="flex items-center justify-start gap-2">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="group flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted/60 hover:text-foreground transition-all cursor-pointer select-none"
          >
            {streaming ? (
              <>
                <Sparkles className="size-3.5 animate-pulse text-brand shrink-0" />
                <span className="text-xs font-medium text-brand">
                  {processingCount > 0
                    ? `Đang suy luận (${processingCount} bước)...`
                    : "Đang suy luận..."}
                </span>
              </>
            ) : (
              <>
                <Brain className="size-3.5 text-muted-foreground/80 group-hover:text-brand shrink-0 transition-colors" />
                <span className="text-xs">Quá trình suy luận</span>
                <span className="rounded bg-muted px-1.5 py-0.2 font-mono text-[10px] text-muted-foreground">
                  {steps.length}
                </span>
              </>
            )}
            <ChevronDown
              className={cn(
                "size-3 text-muted-foreground/70 transition-transform duration-200 group-hover:text-foreground",
                open && "rotate-180"
              )}
            />
          </button>
        </CollapsibleTrigger>
      </div>

      {/* Danh sách các bước suy luận nối theo lề trái */}
      <CollapsibleContent className="mt-2 border-l border-border/60 pl-3 ml-2.5 py-1 space-y-2 animate-in fade-in-0 duration-150">
        {steps.map((step, index) => (
          <StepItem
            key={step.id}
            step={step}
            messageId={messageId}
            isLast={index === steps.length - 1}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

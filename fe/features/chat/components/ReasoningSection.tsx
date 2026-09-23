"use client";

import { useState } from "react";
import { Brain, Check, CheckCircle2, ChevronDown, Copy, Wrench } from "lucide-react";
import type { ReasoningStep, ChoiceOption } from "../types";
import { useChatStore } from "../store";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

/**
 * Format toàn bộ các bước suy luận thành văn bản markdown chi tiết để đưa vào clipboard.
 */
export function formatReasoningSteps(steps: ReasoningStep[]): string {
  if (!steps || steps.length === 0) return "";
  return steps
    .map((step, index) => {
      const num = index + 1;
      const typeBadge =
        step.type === "tool_call" || step.type === "tool_ask"
          ? " [Tool Call]"
          : "";
      let text = `### Bước ${num}: ${step.title}${typeBadge}`;
      if (step.content?.trim()) {
        text += `\n\n${step.content.trim()}`;
      }
      if (step.choice) {
        text += `\n\n**Câu hỏi**: ${step.choice.question}`;
        if (step.choice.options?.length) {
          text +=
            "\n**Phương án**:\n" +
            step.choice.options.map((opt) => `- ${opt.label}`).join("\n");
        }
        if (step.choice.answered) {
          text += `\n**Đã chọn**: ${step.choice.answered.label}`;
        }
      }
      return text;
    })
    .join("\n\n---\n\n");
}

/**
 * Format một bước suy luận đơn lẻ thành văn bản chi tiết đầy đủ để copy.
 */
export function formatSingleStep(step: ReasoningStep, index?: number): string {
  const prefix = typeof index === "number" ? `Bước ${index + 1}: ` : "Bước: ";
  const typeBadge =
    step.type === "tool_call" || step.type === "tool_ask"
      ? " [Tool Call]"
      : "";
  let text = `${prefix}${step.title}${typeBadge}`;
  if (step.content?.trim()) {
    text += `\n\n${step.content.trim()}`;
  }
  if (step.choice) {
    text += `\n\n[Câu hỏi]: ${step.choice.question}`;
    if (step.choice.options?.length) {
      text +=
        `\n[Phương án]:\n` +
        step.choice.options.map((opt) => `- ${opt.label}`).join("\n");
    }
    if (step.choice.answered) {
      text += `\n[Đã chọn]: ${step.choice.answered.label}`;
    }
  }
  return text;
}

function StepItem({
  step,
  messageId,
  index,
}: {
  step: ReasoningStep;
  messageId?: string;
  index?: number;
  isLast?: boolean;
}) {
  const isToolCall = step.type === "tool_call" || step.type === "tool_ask" || !!step.choice;
  const hasChoice = !!step.choice;
  const isAnswered = !!step.choice?.answered;
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const processing = step.status === "processing";

  const handleSelectOption = (option: ChoiceOption) => {
    if (!messageId || !step.choice) return;
    useChatStore.getState().answerChoice(messageId, {
      optionId: option.id,
      label: option.label,
    });
  };

  const handleCopyStep = (e: React.MouseEvent) => {
    e.stopPropagation();
    const text = formatSingleStep(step, index);
    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success(`Đã sao chép: ${step.title}`);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleStepSelectCopy = (e: React.ClipboardEvent) => {
    const text = formatSingleStep(step, index);
    e.clipboardData.setData("text/plain", text);
    e.preventDefault();
    setCopied(true);
    toast.success(`Đã sao chép: ${step.title}`);
    setTimeout(() => setCopied(false), 2000);
  };

  const stepNumber = typeof index === "number" ? String(index + 1).padStart(2, "0") : "01";

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      onCopy={handleStepSelectCopy}
      className="relative flex flex-col gap-1 text-left text-xs"
    >
      <div className="group/item flex w-full items-center gap-2 border-b border-border/40 py-1.5">
        {/* Step index badge */}
        <span className="font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded-md bg-brand/10 text-brand shrink-0">
          {stepNumber}
        </span>

        {/* Tiêu đề & Badges & Nút thao tác */}
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2 overflow-hidden">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center justify-between gap-1.5 text-left transition-colors cursor-pointer overflow-hidden py-0.5"
            >
              <div className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
                <span
                  className={cn(
                    "truncate text-xs transition-colors hover:text-foreground",
                    open ? "font-semibold text-foreground" : "text-muted-foreground font-normal"
                  )}
                  title={step.title}
                >
                  {step.title}
                </span>
                {isToolCall && (
                  <Badge
                    variant="outline"
                    className="shrink-0 border-brand/30 bg-brand/10 text-[10px] text-brand py-0 px-2 font-mono uppercase tracking-wide flex items-center gap-1 rounded-full"
                  >
                    <Wrench className="size-2.5" />
                    Tool
                  </Badge>
                )}
                {hasChoice && isAnswered && (
                  <Badge
                    variant="outline"
                    className="shrink-0 border-emerald-500/30 bg-emerald-500/10 text-[10px] text-emerald-600 dark:text-emerald-400 py-0 px-2 font-medium rounded-full"
                  >
                    <CheckCircle2 className="size-2.5 text-emerald-500 mr-1" />
                    <span className="max-w-[120px] truncate">{step.choice?.answered?.label}</span>
                  </Badge>
                )}
              </div>
              <ChevronDown
                className={cn(
                  "size-3.5 shrink-0 text-muted-foreground transition-transform group-hover/item:text-foreground ml-1",
                  open && "rotate-180"
                )}
              />
            </button>
          </CollapsibleTrigger>

          <div className="flex items-center gap-1 shrink-0">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={handleCopyStep}
                  className="opacity-0 group-hover/item:opacity-100 p-1 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-all cursor-pointer"
                  aria-label="Sao chép bước này"
                >
                  {copied ? (
                    <Check className="size-3 text-brand" />
                  ) : (
                    <Copy className="size-3" />
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">
                {copied ? "Đã sao chép" : "Sao chép bước này"}
              </TooltipContent>
            </Tooltip>
          </div>
        </div>
      </div>

      {/* Chi tiết nội dung bước */}
      <CollapsibleContent className="pl-6 animate-in fade-in-0 duration-150">
        <div className="text-xs leading-relaxed text-muted-foreground space-y-2 py-2">
          {step.content && (
            <div className="rounded-xl border border-border bg-muted/40 p-3 font-mono text-xs text-foreground whitespace-pre-wrap break-words">
              {step.content}
            </div>
          )}
          {processing && (
            <div className="flex items-center gap-2 font-mono text-xs text-brand">
              <span className="size-2 rounded-full bg-brand animate-ping" />
              <span>Đang xử lý bước này...</span>
            </div>
          )}

          {/* Tool Call câu hỏi phương án */}
          {hasChoice && (
            <div className="mt-3 space-y-2.5 border border-border bg-card p-4 rounded-xl shadow-xs">
              <div className="flex items-center gap-2 border-b border-border/60 pb-2">
                <span className="font-mono text-xs font-semibold text-brand">
                  [Câu hỏi làm rõ]
                </span>
                <span className="text-xs font-medium text-foreground">
                  {step.choice?.question}
                </span>
              </div>

              {isAnswered && (
                <div className="flex items-center justify-between border border-brand/30 bg-brand/5 p-2.5 rounded-lg text-xs">
                  <div className="flex items-center gap-2 text-foreground">
                    <span className="size-1.5 rounded-full bg-brand" />
                    <span>Lựa chọn đã ghi nhận: <strong className="text-brand font-semibold">{step.choice?.answered?.label}</strong></span>
                  </div>
                  <Badge variant="outline" className="border-brand/30 bg-brand text-white text-[10px] py-0 px-2 rounded-full">
                    Đã chọn
                  </Badge>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                {step.choice?.options.map((opt) => {
                  const isSelected =
                    step.choice?.answered?.optionId === opt.id ||
                    step.choice?.answered?.label === opt.label;

                  if (isAnswered) {
                    return (
                      <div
                        key={opt.id}
                        className={cn(
                          "flex items-center gap-2 border p-2.5 text-xs rounded-lg font-medium",
                          isSelected
                            ? "border-brand bg-brand/10 text-brand"
                            : "border-border/60 bg-muted/20 text-muted-foreground/60"
                        )}
                      >
                        {isSelected ? <Check className="size-3 text-brand" /> : <span className="size-3" />}
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
                      className="rounded-xl border border-border hover:border-brand/40 hover:bg-muted justify-start text-xs font-normal"
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
  const [copied, setCopied] = useState(false);

  if (!steps || steps.length === 0) return null;

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const fullText = formatReasoningSteps(steps);
    try {
      await navigator.clipboard.writeText(fullText);
      setCopied(true);
      toast.success("Đã sao chép toàn bộ tiến trình suy luận");
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy reasoning steps:", err);
    }
  };

  const handleContainerCopy = (e: React.ClipboardEvent) => {
    const fullText = formatReasoningSteps(steps);
    e.clipboardData.setData("text/plain", fullText);
    e.preventDefault();
    setCopied(true);
    toast.success("Đã sao chép toàn bộ tiến trình suy luận");
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="my-2.5 w-full text-left"
    >
      <div className="flex items-center justify-start gap-2">
        <div
          onCopy={handleContainerCopy}
          className="flex h-9 max-w-full items-center justify-between gap-2 rounded-full border border-border bg-card/80 backdrop-blur-xs px-3.5 py-1 text-xs shadow-xs"
        >
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="group flex min-w-0 flex-1 items-center gap-2 text-left cursor-pointer overflow-hidden select-none"
            >
              {streaming ? (
                <>
                  <span className="size-2 rounded-full bg-brand animate-ping shrink-0" />
                  <span className="font-semibold text-brand shrink-0">
                    Suy luận {processingCount > 0 ? `(${processingCount} đang chạy)` : ""}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground shrink-0">
                    [{steps.length} bước]
                  </span>
                </>
              ) : (
                <>
                  <Brain className="size-3.5 text-brand shrink-0" />
                  <span className="font-medium text-foreground shrink-0">
                    Tiến trình suy luận
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground shrink-0">
                    [{steps.length} bước]
                  </span>
                </>
              )}
              <ChevronDown
                className={cn(
                  "size-3.5 shrink-0 text-muted-foreground transition-transform duration-150 group-hover:text-foreground ml-auto",
                  open && "rotate-180"
                )}
              />
            </button>
          </CollapsibleTrigger>

          <div className="flex items-center shrink-0 border-l border-border pl-2 ml-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="p-1 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors cursor-pointer"
                  aria-label="Sao chép toàn bộ suy luận"
                >
                  {copied ? (
                    <Check className="size-3 text-brand" />
                  ) : (
                    <Copy className="size-3" />
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">
                {copied ? "Đã sao chép" : "Sao chép toàn bộ"}
              </TooltipContent>
            </Tooltip>
          </div>
        </div>
      </div>

      <CollapsibleContent
        onCopy={handleContainerCopy}
        className="mt-2 border-l-2 border-brand/25 pl-4 ml-3 py-1 space-y-1 animate-in fade-in-0 duration-150"
      >
        {steps.map((step, index) => (
          <StepItem
            key={step.id}
            step={step}
            index={index}
            messageId={messageId}
            isLast={index === steps.length - 1}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

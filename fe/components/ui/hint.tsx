"use client";

import { CircleHelp } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface HintProps {
  // hướng dẫn đầy đủ; nhãn trên giao diện chỉ giữ 1–2 từ
  content: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  className?: string;
  children: React.ReactElement;
}

// TooltipContent mặc định là chữ HOA mono cho nhãn ngắn; câu hướng dẫn cần chữ thường, xuống dòng được
export function Hint({ content, side = "top", className, children }: HintProps) {
  return (
    <Tooltip delayDuration={250}>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent
        side={side}
        sideOffset={6}
        className={cn(
          "max-w-64 rounded-lg border-border bg-popover px-3 py-2 font-sans text-xs font-normal normal-case leading-relaxed tracking-normal text-popover-foreground shadow-md dark:bg-popover",
          className
        )}
      >
        {content}
      </TooltipContent>
    </Tooltip>
  );
}

// dấu "?" nhỏ cạnh nhãn: nhãn giữ ngắn, giải thích đầy đủ hiện khi hover/focus
export function HintIcon({ content, side = "top" }: { content: React.ReactNode; side?: HintProps["side"] }) {
  return (
    <Hint content={content} side={side}>
      <button type="button" aria-label="Giải thích" className="inline-flex size-4 cursor-help items-center justify-center rounded-full text-muted-foreground/70 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
        <CircleHelp className="size-3.5" />
      </button>
    </Hint>
  );
}

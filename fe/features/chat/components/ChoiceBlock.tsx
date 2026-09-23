"use client";

import { useState } from "react";
import { Check, HelpCircle, SendHorizonal } from "lucide-react";
import type { MessageChoice } from "../types";
import { useChatStore } from "../store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";

export function ChoiceBlock({
  messageId,
  choice,
}: {
  messageId: string;
  choice: MessageChoice;
}) {
  const answerChoice = useChatStore((s) => s.answerChoice);
  const [custom, setCustom] = useState("");
  const answered = choice.answered;
  const canSubmit = custom.trim().length > 0;

  const submitCustom = () => {
    const text = custom.trim();
    if (!text) return;
    answerChoice(messageId, {
      optionId: "custom",
      label: text,
      custom: true,
    });
    setCustom("");
  };

  return (
    <div className="mt-3 flex flex-col gap-2.5">
      {answered ? (
        <Alert className="border border-brand/30 bg-brand/5 text-foreground px-4 py-3 rounded-xl shadow-xs">
          <div className="flex items-center gap-2.5">
            <Check className="size-4 shrink-0 text-brand" />
            <AlertDescription className="text-xs font-medium text-foreground">
              <span className="text-brand font-semibold mr-1.5">[Đã xác nhận]</span>
              {answered.label}
            </AlertDescription>
          </div>
        </Alert>
      ) : (
        <>
          <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
            <HelpCircle className="size-3.5 text-brand" />
            <span>Lựa chọn phương án:</span>
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {choice.options.map((option, idx) => (
              <Button
                key={option.id}
                variant="outline"
                onClick={() =>
                  answerChoice(messageId, {
                    optionId: option.id,
                    label: option.label,
                  })
                }
                className="group relative h-auto justify-start rounded-xl border border-border bg-card/60 px-3.5 py-2.5 text-left text-xs font-normal text-foreground transition-all duration-200 hover:border-brand/40 hover:bg-muted hover:text-brand"
              >
                <span className="font-mono text-[10px] text-muted-foreground mr-2 shrink-0 group-hover:text-brand font-semibold">
                  [{String(idx + 1).padStart(2, "0")}]
                </span>
                <span className="flex-1 leading-snug">{option.label}</span>
              </Button>
            ))}
          </div>

          <div className="relative my-1 flex items-center">
            <Separator className="flex-1 h-px bg-border/60" />
            <span className="px-2 text-[10px] font-mono uppercase text-muted-foreground tracking-wider bg-background">
              Hoặc tự nhập
            </span>
            <Separator className="flex-1 h-px bg-border/60" />
          </div>

          <div className="flex items-center gap-2">
            <Input
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitCustom();
              }}
              placeholder="Nhập phương án của bạn..."
              className="h-10 min-w-0 flex-1 text-xs rounded-xl"
            />
            <Button
              onClick={submitCustom}
              disabled={!canSubmit}
              aria-label="Gửi phương án tự nhập"
              className="h-10 px-4 shrink-0 rounded-xl"
            >
              <SendHorizonal className="size-4 mr-1.5" />
              <span>Gửi</span>
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

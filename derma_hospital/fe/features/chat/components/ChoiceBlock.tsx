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
    <div className="mt-2.5 flex flex-col gap-1.5">
      {answered ? (
        <Alert className="border-brand/40 bg-brand/10 text-foreground px-3 py-2">
          <div className="flex items-center gap-2">
            <Check className="size-3.5 shrink-0 text-brand" />
            <AlertDescription className="text-xs font-medium text-foreground">
              Bạn đã chọn: {answered.label}
            </AlertDescription>
          </div>
        </Alert>
      ) : (
        <>
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <HelpCircle className="size-3.5" />
            <span>Chọn một lựa chọn:</span>
          </p>
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {choice.options.map((option) => (
              <Button
                key={option.id}
                variant="outline"
                onClick={() =>
                  answerChoice(messageId, {
                    optionId: option.id,
                    label: option.label,
                  })
                }
                className="h-auto justify-start whitespace-normal rounded-xl border-border bg-background px-3 py-2 text-left text-sm text-muted-foreground font-normal transition-colors hover:border-brand/40 hover:bg-brand/5 hover:text-foreground"
              >
                {option.label}
              </Button>
            ))}
          </div>

          <div className="flex items-center gap-2 pt-1">
            <Separator className="flex-1" />
            <span className="text-[11px] text-muted-foreground">
              Hoặc tự nhập phương án
            </span>
            <Separator className="flex-1" />
          </div>

          <div className="flex items-center gap-2">
            <Input
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitCustom();
              }}
              placeholder="Nhập phương án của bạn..."
              className="h-9 min-w-0 flex-1 text-sm"
            />
            <Button
              size="icon"
              onClick={submitCustom}
              disabled={!canSubmit}
              aria-label="Gửi phương án tự nhập"
              className="size-9 shrink-0"
            >
              <SendHorizonal className="size-4" />
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

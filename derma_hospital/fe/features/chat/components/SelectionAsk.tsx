"use client";

import { useEffect, useRef, useState } from "react";
import { CornerUpLeft } from "lucide-react";
import { useSelectionStore } from "../selectionStore";
import { useChatStore } from "../store";
import { Button } from "@/components/ui/button";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { cn } from "@/lib/utils";

interface PendingSelection {
  text: string;
  x: number;
  y: number;
}

/** Bôi đen hoặc Chuột phải vào đoạn tin nhắn -> Context Menu / Nút "Hỏi" shadcn -> đẩy pending xuống thanh nhập */
export function SelectionAsk({
  messageId,
  containerRef,
  className,
  children,
}: {
  messageId: string;
  containerRef?: React.RefObject<HTMLElement | null>;
  className?: string;
  children?: React.ReactNode;
}) {
  const setPending = useSelectionStore((s) => s.setPending);
  const [selection, setSelection] = useState<PendingSelection | null>(null);
  const [visible, setVisible] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Bắt sự kiện bôi đen trong nội dung tin nhắn
  useEffect(() => {
    if (!containerRef?.current) return;
    const container = containerRef.current;
    const onMouseUp = () => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
        setVisible(false);
        return;
      }
      const text = sel.toString().trim();
      if (!text) {
        setVisible(false);
        return;
      }
      const range = sel.getRangeAt(0);
      if (
        !container.contains(range.startContainer) ||
        !container.contains(range.endContainer)
      ) {
        return;
      }
      const rect = range.getBoundingClientRect();
      setSelection({
        text,
        x: rect.left + rect.width / 2,
        y: rect.top,
      });
      setVisible(true);
    };
    container.addEventListener("mouseup", onMouseUp);
    return () => container.removeEventListener("mouseup", onMouseUp);
  }, [containerRef, messageId]);

  // Ẩn khi bấm ra ngoài nút
  useEffect(() => {
    if (!visible) return;
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (buttonRef.current && !buttonRef.current.contains(target)) {
        setVisible(false);
      }
    };
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [visible]);

  const askText = (textToAsk?: string) => {
    const text = textToAsk || selection?.text || window.getSelection()?.toString().trim();
    if (!text) return;
    useSelectionStore.getState().addPendingSelection({
      source: "message",
      refId: messageId,
      text,
    });
    setVisible(false);
    setSelection(null);
    window.getSelection()?.removeAllRanges();
  };

  const floatingButton = (
    <Button
      ref={buttonRef}
      type="button"
      size="sm"
      onClick={() => askText()}
      aria-hidden={!visible}
      tabIndex={visible ? 0 : -1}
      className={cn(
        "fixed z-50 h-7 rounded-full border border-brand/40 bg-popover px-2.5 text-xs font-medium text-popover-foreground shadow-md transition-all hover:bg-brand hover:text-brand-foreground cursor-pointer gap-1 items-center",
        visible ? "flex" : "pointer-events-none invisible opacity-0"
      )}
      style={{
        left: selection?.x ?? 0,
        top: (selection?.y ?? 0) - 8,
        transform: "translate(-50%, -100%)",
      }}
    >
      <CornerUpLeft className="size-3 shrink-0 text-current" />
      <span>Hỏi</span>
    </Button>
  );

  if (children) {
    return (
      <ContextMenu>
        <ContextMenuTrigger asChild>
          <div className={cn("relative", className)}>
            {children}
            {floatingButton}
          </div>
        </ContextMenuTrigger>
        <ContextMenuContent className="w-32">
          <ContextMenuItem onClick={() => askText()} className="cursor-pointer gap-2 text-xs font-medium">
            <CornerUpLeft className="size-3.5 text-brand" />
            <span>Hỏi</span>
          </ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>
    );
  }

  return floatingButton;
}

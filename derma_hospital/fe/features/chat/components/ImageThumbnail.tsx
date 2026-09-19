"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface ImageThumbnailProps {
  url: string;
  name: string;
  size?: number;
  className?: string;
}

/** Ảnh thu nhỏ, click để xem full-size trong dialog — dùng chung cho ảnh đính kèm
 * đang soạn (`ChatInput.tsx`) và ảnh trong tin nhắn đã gửi (`MessageBubble.tsx`). */
export function ImageThumbnail({ url, name, size = 32, className }: ImageThumbnailProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`Xem ảnh ${name}`}
        className={cn(
          "shrink-0 overflow-hidden rounded-md border border-border/60 cursor-pointer transition-opacity hover:opacity-80",
          className
        )}
        style={{ width: size, height: size }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={url} alt={name} className="size-full object-cover" />
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl p-3 sm:p-4">
          <DialogHeader>
            <DialogTitle className="truncate text-sm font-medium">{name}</DialogTitle>
          </DialogHeader>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={url}
            alt={name}
            className="max-h-[75vh] w-full rounded-md object-contain"
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

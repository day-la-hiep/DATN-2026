"use client";

import { useState, useEffect, useCallback } from "react";
import {
  ZoomIn,
  ZoomOut,
  RotateCw,
  RefreshCw,
  ExternalLink,
  X,
  Loader2,
  FileImage,
} from "lucide-react";
import { Dialog, DialogPortal } from "@/components/ui/dialog";
import { Dialog as DialogPrimitive } from "radix-ui";
import { cn, formatBytes } from "@/lib/utils";

export interface ImageThumbnailProps {
  url: string;
  name: string;
  /** Kích thước thumbnail (px), mặc định 72 */
  size?: number;
  className?: string;
  fileSize?: number;
  /** Trạng thái đang upload lên server */
  uploading?: boolean;
  /** Callback gỡ file khỏi danh sách đính kèm */
  onRemove?: () => void;
}

/**
 * Thumbnail xem trước ảnh khi upload và trong tin nhắn.
 * Khi nhấp vào sẽ mở Modal Lightbox độ phân giải cao, hỗ trợ:
 * - Zoom phóng to tối đa 500% (nút bấm, cuộn chuột wheel, nhấp đúp 2x)
 * - Kéo rê (pan/drag) ảnh khi đã phóng to để soi rõ chi tiết bệnh lý/da
 * - Xoay ảnh 90° (hữu ích cho ảnh chụp từ điện thoại)
 * - Đặt lại kích thước, mở ảnh gốc tab mới, phím tắt tiện lợi
 */
export function ImageThumbnail({
  url,
  name,
  size = 72,
  className,
  fileSize,
  uploading = false,
  onRemove,
}: ImageThumbnailProps) {
  const [open, setOpen] = useState(false);
  const [scale, setScale] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [dimensions, setDimensions] = useState<{ w: number; h: number } | null>(null);

  const handleOpenChange = useCallback((isOpen: boolean) => {
    setOpen(isOpen);
    if (!isOpen) {
      setScale(1);
      setRotation(0);
      setPosition({ x: 0, y: 0 });
      setIsDragging(false);
    }
  }, []);

  // Phím tắt bàn phím khi lightbox mở
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        setScale((s) => Math.min(Number((s + 0.25).toFixed(2)), 5));
      } else if (e.key === "-" || e.key === "_") {
        e.preventDefault();
        setScale((s) => {
          const next = Math.max(Number((s - 0.25).toFixed(2)), 0.5);
          if (next <= 1) setPosition({ x: 0, y: 0 });
          return next;
        });
      } else if (e.key === "0") {
        e.preventDefault();
        setScale(1);
        setRotation(0);
        setPosition({ x: 0, y: 0 });
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        setRotation((r) => (r + 90) % 360);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  const handleZoomIn = useCallback(() => {
    setScale((s) => Math.min(Number((s + 0.25).toFixed(2)), 5));
  }, []);

  const handleZoomOut = useCallback(() => {
    setScale((s) => {
      const next = Math.max(Number((s - 0.25).toFixed(2)), 0.5);
      if (next <= 1) setPosition({ x: 0, y: 0 });
      return next;
    });
  }, []);

  const handleReset = useCallback(() => {
    setScale(1);
    setRotation(0);
    setPosition({ x: 0, y: 0 });
  }, []);

  const handleRotate = useCallback(() => {
    setRotation((r) => (r + 90) % 360);
  }, []);

  const handleDoubleClick = useCallback(() => {
    if (scale > 1) {
      setScale(1);
      setPosition({ x: 0, y: 0 });
    } else {
      setScale(2);
    }
  }, [scale]);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.25 : -0.25;
    setScale((s) => {
      const next = Math.min(Math.max(0.5, Number((s + delta).toFixed(2))), 5);
      if (next <= 1) setPosition({ x: 0, y: 0 });
      return next;
    });
  }, []);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (scale <= 1) return;
      e.preventDefault();
      setIsDragging(true);
      setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
      (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    },
    [scale, position]
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging || scale <= 1) return;
      e.preventDefault();
      setPosition({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    },
    [isDragging, scale, dragStart]
  );

  const handlePointerUp = useCallback((e: React.PointerEvent) => {
    setIsDragging(false);
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);
    } catch {
      // Bỏ qua lỗi nếu con trỏ đã nhả
    }
  }, []);

  // Tính toán vị trí render (nếu scale <= 1 thì luôn đưa về tâm)
  const renderPos = scale <= 1 ? { x: 0, y: 0 } : position;

  return (
    <>
      {/* Thumbnail hiển thị bên ngoài */}
      <div
        className={cn(
          "group relative shrink-0 overflow-hidden rounded-xl border border-border bg-muted/40 shadow-xs transition-all hover:border-brand/40 hover:shadow-md",
          className
        )}
        style={{ width: size, height: size }}
      >
        <button
          type="button"
          onClick={() => handleOpenChange(true)}
          aria-label={`Xem ảnh ${name}`}
          title="Nhấp để phóng to ảnh chi tiết"
          className="size-full cursor-pointer overflow-hidden p-0 text-left outline-hidden"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={url}
            alt={name}
            className="size-full object-cover transition-transform duration-300 group-hover:scale-105"
          />

          {/* Lớp phủ hover với icon kính lúp */}
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
            <ZoomIn className="size-5 text-white drop-shadow-md" />
          </div>
        </button>

        {/* Lớp phủ trạng thái đang upload */}
        {uploading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/75 backdrop-blur-xs pointer-events-none">
            <Loader2 className="size-4 animate-spin text-brand" />
            <span className="mt-1 text-[9px] font-medium text-foreground">Đang tải...</span>
          </div>
        )}

        {/* Nút xóa ảnh góc trên phải (nếu có onRemove) */}
        {onRemove && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            aria-label={`Gỡ ảnh ${name}`}
            title="Gỡ ảnh này"
            className="absolute top-1 right-1 z-10 flex size-5 items-center justify-center rounded-full bg-black/65 text-white shadow-xs transition-colors hover:bg-destructive cursor-pointer"
          >
            <X className="size-3" />
          </button>
        )}

        {/* Badge dung lượng file ở đáy ảnh */}
        {fileSize !== undefined && (
          <div className="pointer-events-none absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/75 via-black/40 to-transparent px-1 py-0.5">
            <p className="truncate text-center text-[9px] font-medium text-white/95">
              {formatBytes(fileSize)}
            </p>
          </div>
        )}
      </div>

      {/* Lightbox Modal Xem Ảnh To Toàn Diện */}
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogPortal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0" />

          <DialogPrimitive.Content
            className="fixed inset-2 sm:inset-4 md:inset-6 z-50 flex flex-col overflow-hidden rounded-2xl border border-white/20 bg-neutral-950 text-white shadow-2xl outline-none data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95"
            aria-describedby={undefined}
          >
            {/* Header thanh công cụ trên */}
            <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/10 bg-neutral-900/80 backdrop-blur-md px-4 sm:px-6">
              <div className="flex min-w-0 items-center gap-2.5">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-brand text-white">
                  <FileImage className="size-4" />
                </div>
                <DialogPrimitive.Title className="truncate font-sans text-xs font-semibold text-neutral-100 max-w-60 sm:max-w-md">
                  {name}
                </DialogPrimitive.Title>
                {fileSize !== undefined && (
                  <span className="hidden sm:inline-block rounded-full border border-white/20 bg-white/10 px-2.5 py-0.5 font-mono text-[10px] text-neutral-300">
                    {formatBytes(fileSize)}
                  </span>
                )}
                {dimensions && (
                  <span className="hidden md:inline-block rounded-full border border-white/20 bg-white/10 px-2.5 py-0.5 font-mono text-[10px] text-neutral-300">
                    {dimensions.w} × {dimensions.h} px
                  </span>
                )}
              </div>

              {/* Hướng dẫn thao tác & Nút đóng */}
              <div className="flex items-center gap-3">
                <p className="hidden lg:block font-mono text-[10px] text-neutral-400">
                  Cuộn chuột: Zoom • Kéo: Di chuyển • Nhấp đúp: 2x
                </p>
                <div className="flex items-center gap-1.5">
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex size-8 items-center justify-center rounded-lg border border-white/20 text-neutral-300 hover:bg-white hover:text-black transition-colors cursor-pointer"
                    title="Mở ảnh gốc trong tab mới"
                  >
                    <ExternalLink className="size-4" />
                  </a>
                  <DialogPrimitive.Close
                    className="flex size-8 items-center justify-center rounded-lg border border-white/20 text-neutral-300 hover:bg-brand hover:border-brand hover:text-white transition-colors cursor-pointer"
                    aria-label="Đóng (Esc)"
                    title="Đóng (Esc)"
                  >
                    <X className="size-5" />
                  </DialogPrimitive.Close>
                </div>
              </div>
            </div>

            {/* Khung hiển thị ảnh chính */}
            <div
              onWheel={handleWheel}
              onDoubleClick={handleDoubleClick}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
              className={cn(
                "relative flex flex-1 items-center justify-center overflow-hidden p-2 sm:p-6 select-none",
                scale > 1
                  ? isDragging
                    ? "cursor-grabbing"
                    : "cursor-grab"
                  : "cursor-zoom-in"
              )}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={url}
                alt={name}
                draggable={false}
                onLoad={(e) => {
                  setDimensions({
                    w: e.currentTarget.naturalWidth,
                    h: e.currentTarget.naturalHeight,
                  });
                }}
                style={{
                  transform: `translate3d(${renderPos.x}px, ${renderPos.y}px, 0) scale(${scale}) rotate(${rotation}deg)`,
                  transition: isDragging
                    ? "none"
                    : "transform 180ms cubic-bezier(0.16, 1, 0.3, 1)",
                }}
                className="max-h-full max-w-full rounded-lg object-contain will-change-transform shadow-2xl"
              />
            </div>

            {/* Thanh điều khiển nổi ở đáy */}
            <div className="pointer-events-none absolute bottom-5 inset-x-0 z-20 flex justify-center px-4">
              <div className="pointer-events-auto flex items-center gap-1.5 rounded-full border border-white/20 bg-neutral-900/90 backdrop-blur-md px-3.5 py-1.5 shadow-xl text-white">
                <button
                  type="button"
                  onClick={handleZoomOut}
                  disabled={scale <= 0.5}
                  title="Thu nhỏ (-)"
                  className="flex size-7 items-center justify-center rounded-full text-neutral-200 hover:bg-white hover:text-black disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
                >
                  <ZoomOut className="size-4" />
                </button>

                <button
                  type="button"
                  onClick={handleReset}
                  title="Nhấp để đặt lại 100% (0)"
                  className="px-2 py-0.5 font-mono text-xs font-semibold text-neutral-100 hover:bg-white hover:text-black rounded-md transition-colors cursor-pointer"
                >
                  {Math.round(scale * 100)}%
                </button>

                <button
                  type="button"
                  onClick={handleZoomIn}
                  disabled={scale >= 5}
                  title="Phóng to (+)"
                  className="flex size-7 items-center justify-center rounded-full text-neutral-200 hover:bg-white hover:text-black disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
                >
                  <ZoomIn className="size-4" />
                </button>

                <div className="h-4 w-px bg-white/30 mx-1" />

                <button
                  type="button"
                  onClick={handleRotate}
                  title="Xoay 90° (R)"
                  className="flex size-7 items-center justify-center rounded-full text-neutral-200 hover:bg-white hover:text-black transition-colors cursor-pointer"
                >
                  <RotateCw className="size-4" />
                </button>

                <button
                  type="button"
                  onClick={handleReset}
                  title="Đặt lại ban đầu (0)"
                  className="flex size-7 items-center justify-center rounded-full text-neutral-200 hover:bg-white hover:text-black transition-colors cursor-pointer"
                >
                  <RefreshCw className="size-3.5" />
                </button>
              </div>
            </div>
          </DialogPrimitive.Content>
        </DialogPortal>
      </Dialog>
    </>
  );
}

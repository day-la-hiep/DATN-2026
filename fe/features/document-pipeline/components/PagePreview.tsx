"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ImageOff } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { errorMessage, documentApi } from "../api";

type View = "image" | "text";

/** Ảnh trang PDF hoặc chữ đã đọc; `caption` nói vì sao đang xem trang này, `highlightLine` tô dòng neo. */
export function PagePreview({
  documentId,
  page,
  total,
  caption,
  highlightLine,
  onPage,
}: {
  documentId: string;
  page: number;
  total?: number | null;
  caption?: React.ReactNode;
  highlightLine?: number | null;
  onPage: (p: number) => void;
}) {
  const [view, setView] = useState<View>("image");
  const [draft, setDraft] = useState<string | null>(null);
  const clamp = (p: number) => Math.max(1, total ? Math.min(total, p) : p);

  const image = useQuery({
    queryKey: ["toc", documentId, "pageimg", page],
    queryFn: () => documentApi.pageImageUrl(documentId, page),
    enabled: view === "image",
    staleTime: Infinity,
    gcTime: 10 * 60_000,
  });
  const text = useQuery({
    queryKey: ["toc", documentId, "pagetext", page],
    queryFn: () => documentApi.page(documentId, page),
    staleTime: 60_000,
  });

  const go = () => {
    const n = parseInt(draft ?? "", 10);
    setDraft(null);
    if (n > 0) onPage(clamp(n));
  };
  const lines = (text.data?.text ?? "").split("\n");

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-border bg-card">
      <div className="space-y-2 border-b border-border p-3">
        <div className="flex items-center gap-1.5">
          <Button variant="outline" size="icon-xs" disabled={page <= 1} onClick={() => onPage(clamp(page - 1))} aria-label="Trang trước">
            <ChevronLeft />
          </Button>
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <span>Trang</span>
            <Input
              value={draft ?? String(page)}
              onChange={(e) => setDraft(e.target.value.replace(/\D/g, ""))}
              onFocus={(e) => e.currentTarget.select()}
              onBlur={go}
              onKeyDown={(e) => e.key === "Enter" && go()}
              inputMode="numeric"
              className="h-7 w-16 rounded-lg px-2 text-center font-mono text-xs"
              aria-label="Số trang trong file PDF"
            />
            {total ? <span className="tabular-nums">/ {total}</span> : null}
          </div>
          <Button variant="outline" size="icon-xs" disabled={total ? page >= total : false} onClick={() => onPage(clamp(page + 1))} aria-label="Trang sau">
            <ChevronRight />
          </Button>
          <div className="flex-1" />
          <div className="inline-flex rounded-lg border border-border p-0.5 text-[11px] font-medium">
            {(["image", "text"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                className={cn(
                  "cursor-pointer rounded-md px-2 py-0.5 transition-colors",
                  view === v ? "bg-brand/10 text-brand" : "text-muted-foreground hover:text-foreground"
                )}
              >
                {v === "image" ? "Hình ảnh" : "Văn bản"}
              </button>
            ))}
          </div>
        </div>
        <p className="min-h-4 text-[11px] leading-relaxed text-muted-foreground">
          {caption}
          {text.data && text.data.page_printed !== page && (
            <span className="ml-1.5 font-mono">· số trang in {text.data.page_printed}</span>
          )}
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-auto bg-muted/30 p-3">
        {view === "image" ? (
          image.isLoading ? (
            <Skeleton className="aspect-[3/4] w-full rounded-lg" />
          ) : image.isError || !image.data ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center text-xs text-muted-foreground">
              <ImageOff className="size-5" />
              {image.isError ? errorMessage(image.error) : "Không hiển thị được hình ảnh trang."}
            </div>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={image.data} alt={`Trang PDF ${page}`} className="w-full rounded-lg border border-border bg-white" />
          )
        ) : text.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 10 }).map((_, i) => (
              <Skeleton key={i} className="h-4 w-full" />
            ))}
          </div>
        ) : text.isError ? (
          <p className="text-xs text-muted-foreground">{errorMessage(text.error)} (có thể trang này chưa được đọc ở bước Đọc nội dung)</p>
        ) : (
          <div className="font-mono text-[11px] leading-relaxed break-words whitespace-pre-wrap text-foreground">
            {lines.map((ln, i) => (
              <div key={i} className={cn(i === highlightLine && "rounded bg-amber-300/50 px-0.5")}>
                {ln || " "}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Số trang bấm được: đưa khung xem trang tới trang đó. */
export function PageChip({ page, onOpen, active }: { page: number; onOpen: (p: number) => void; active?: boolean }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onOpen(page);
      }}
      className={cn(
        "cursor-pointer rounded-md px-1.5 py-0.5 font-mono text-[11px] tabular-nums transition-colors",
        active ? "bg-brand/15 text-brand" : "bg-muted text-brand hover:bg-brand/10"
      )}
      title="Xem trang này"
    >
      tr.{page}
    </button>
  );
}

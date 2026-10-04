"use client";

import { useQuery } from "@tanstack/react-query";
import { ImageOff } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { documentApi } from "../api";
import { useData } from "../hooks";
import type { Figure } from "../types";
import { EmptyState } from "./bits";
import { PageChip } from "./PagePreview";

/** Một hình: ảnh tải bằng axios (cần token) rồi hiển thị qua object URL, kèm trang và chú thích của sách. */
function FigureCard({ documentId, f, onPreview }: { documentId: string; f: Figure; onPreview: (p: number) => void }) {
  const img = useQuery({
    queryKey: ["toc", documentId, "figimg", f.figureId],
    queryFn: () => documentApi.figureImageUrl(documentId, f.figureId),
    staleTime: Infinity,
    gcTime: 10 * 60_000,
  });
  return (
    <article className="space-y-2 rounded-2xl border border-border bg-card p-3">
      <div className="flex aspect-[4/3] items-center justify-center overflow-hidden rounded-lg bg-muted">
        {img.data ? (
          <a href={img.data} target="_blank" rel="noreferrer" title="Mở ảnh gốc">
            <img src={img.data} alt={f.caption || `Hình trang ${f.page}`} className="max-h-full max-w-full object-contain" />
          </a>
        ) : img.isError ? (
          <ImageOff className="size-6 text-muted-foreground" />
        ) : (
          <Skeleton className="size-full" />
        )}
      </div>
      <div className="flex items-center gap-1.5 text-[11px]">
        <span className="rounded bg-muted px-1.5 py-0.5 font-mono">{f.figureId.split(":").pop()}</span>
        <PageChip page={f.page} onOpen={onPreview} />
      </div>
      <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground">{f.caption || "(không có chú thích)"}</p>
    </article>
  );
}

/** Danh sách hình ảnh trích từ sách (bước Đọc nội dung, engine docling). */
export function FigureBrowser({ documentId, onPreview }: { documentId: string; onPreview: (p: number) => void }) {
  const list = useData(documentId, "figures", {}, () => documentApi.figures(documentId));
  const items = list.data ?? [];
  if (list.data && items.length === 0) {
    return (
      <EmptyState
        title="Chưa có hình ảnh"
        hint="Ảnh chỉ được trích khi đọc bằng engine Docling (Cài đặt). Engine pdftotext không trích ảnh."
      />
    );
  }
  return (
    <section className="space-y-3">
      <h3 className="text-sm font-medium">Hình ảnh trong sách ({items.length})</h3>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((f) => (
          <FigureCard key={f.figureId} documentId={documentId} f={f} onPreview={onPreview} />
        ))}
      </div>
    </section>
  );
}

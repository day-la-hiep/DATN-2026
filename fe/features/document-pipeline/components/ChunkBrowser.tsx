"use client";

import { ChevronRight, Download } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Chips, EmptyState, Pager, SearchBox } from "./bits";
import { errorMessage, documentApi } from "../api";
import { LEVEL_TONE } from "../constants";
import { useData, usePage } from "../hooks";
import type { Chunk, TocDoc, TocEntry } from "../types";
import { PageChip } from "./PagePreview";

const PAGE_SIZE = 20;

/** Cây điều hướng part → section → mục (chỉ mục có chunk). Mục con hiện khi cha được mở. */
function TocNav({
  entries,
  perNode,
  selected,
  onSelect,
}: {
  entries: TocEntry[];
  perNode: Record<string, number>;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const withChunks = useMemo(() => entries.filter((e) => perNode[e.id]), [entries, perNode]);
  const hasChild = useMemo(() => new Set(withChunks.map((e) => e.parentId).filter(Boolean) as string[]), [withChunks]);
  const byId = useMemo(() => new Map(withChunks.map((e) => [e.id, e])), [withChunks]);
  // mục hiển thị khi mọi tổ tiên (còn trong cây) đang mở
  const visible = withChunks.filter((e) => {
    let p = e.parentId ? byId.get(e.parentId) : undefined;
    while (p) {
      if (!open.has(p.id)) return false;
      p = p.parentId ? byId.get(p.parentId) : undefined;
    }
    return true;
  });
  const toggle = (id: string) =>
    setOpen((s) => {
      const n = new Set(s);
      if (!n.delete(id)) n.add(id);
      return n;
    });

  return (
    <nav className="max-h-[70vh] space-y-0.5 overflow-y-auto pr-1" aria-label="Mục lục">
      <button
        type="button"
        onClick={() => onSelect("")}
        className={cn(
          "flex w-full cursor-pointer items-center rounded-lg px-2 py-1 text-left text-xs font-medium transition-colors",
          selected === "" ? "bg-brand/10 text-brand" : "text-muted-foreground hover:bg-muted"
        )}
      >
        Toàn bộ sách
      </button>
      {visible.map((e) => (
        <div
          key={e.id}
          className={cn(
            "flex items-center gap-0.5 rounded-lg pr-1.5 transition-colors",
            selected === e.id ? "bg-brand/10" : "hover:bg-muted"
          )}
          style={{ paddingLeft: `${e.level * 12}px` }}
        >
          {hasChild.has(e.id) ? (
            <button
              type="button"
              onClick={() => toggle(e.id)}
              className="flex size-5 shrink-0 cursor-pointer items-center justify-center text-muted-foreground"
              aria-label={open.has(e.id) ? "Thu gọn" : "Mở rộng"}
            >
              <ChevronRight className={cn("size-3 transition-transform", open.has(e.id) && "rotate-90")} />
            </button>
          ) : (
            <span className="size-5 shrink-0" />
          )}
          <button
            type="button"
            onClick={() => onSelect(e.id)}
            className={cn("min-w-0 flex-1 cursor-pointer truncate py-1 text-left text-xs", e.level <= 1 && "font-semibold", selected === e.id ? "text-brand" : LEVEL_TONE[e.level])}
            title={e.title}
          >
            {e.title}
          </button>
          <span className="font-mono text-[10px] text-muted-foreground tabular-nums">{perNode[e.id]}</span>
        </div>
      ))}
    </nav>
  );
}

function ChunkCard({ c, onPreview, previewPage }: { c: Chunk; onPreview: (p: number) => void; previewPage: number }) {
  const [open, setOpen] = useState(false);
  const long = c.text.length > 320;
  const crumbs = [c.part, c.section, c.topic, c.subtopic].filter(Boolean);
  return (
    <article className="space-y-2 rounded-2xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-muted-foreground">
        {crumbs.map((h, i) => (
          <span key={`${h}-${i}`} className="flex items-center gap-1.5">
            {i > 0 && <span>›</span>}
            <span className={i === crumbs.length - 1 ? "font-medium text-foreground" : "max-w-48 truncate"} title={h}>
              {h}
            </span>
          </span>
        ))}
        {crumbs.length === 0 && <span className="italic">(không thuộc mục nào trong mục lục)</span>}
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="rounded bg-muted px-1.5 py-0.5 font-mono">{c.chunkId.split(":").pop()}</span>
        <PageChip page={c.pageStart} onOpen={onPreview} active={previewPage >= c.pageStart && previewPage <= c.pageEnd} />
        {c.pageEnd !== c.pageStart && <PageChip page={c.pageEnd} onOpen={onPreview} />}
        <span className="text-muted-foreground" title="Trang in của sách">
          in {c.pagePrintedStart}
          {c.pagePrintedEnd !== c.pagePrintedStart && `–${c.pagePrintedEnd}`}
        </span>
        {c.pagesHint && (
          <span className="text-muted-foreground" title="Khoảng trang của mục theo mục lục">
            mục: tr.{c.pagesHint[0]}
            {c.pagesHint[1] !== c.pagesHint[0] && `–${c.pagesHint[1]}`}
          </span>
        )}
        {c.boundary && (
          <span
            className="rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-600 dark:text-amber-400"
            title="Chưa tìm thấy dòng tiêu đề của mục: vị trí bắt đầu mục chỉ chính xác đến trang"
          >
            vị trí mục chưa chắc
          </span>
        )}
        {c.suspect && <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-600 dark:text-amber-400">mục cần kiểm tra</span>}
        <span className={cn("tabular-nums", c.reviewReason && /dài|ngắn/.test(c.reviewReason) ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground")}>
          ~{Math.round(c.tokens / 1.3)} từ
        </span>
      </div>
      <p className="text-xs leading-relaxed whitespace-pre-wrap text-foreground">
        {open || !long ? c.text : c.text.slice(0, 320) + "…"}
      </p>
      {long && (
        <button type="button" onClick={() => setOpen(!open)} className="cursor-pointer text-[11px] text-brand hover:underline">
          {open ? "Thu gọn" : "Xem đầy đủ"}
        </button>
      )}
    </article>
  );
}

export function ChunkBrowser({
  documentId,
  toc,
  previewPage,
  onPreview,
}: {
  documentId: string;
  toc?: TocDoc;
  previewPage: number;
  onPreview: (p: number) => void;
}) {
  const [q, setQ] = useState("");
  const [node, setNode] = useState("");
  const [only, setOnly] = useState("all");
  const [page, setPage] = usePage(`${q}|${node}|${only}`);
  const list = useData(documentId, "chunks", { q, node, only, page }, () =>
    documentApi.chunks(documentId, { q, node, onlyReview: only === "review", page, pageSize: PAGE_SIZE })
  );
  const data = list.data;
  const counts = data?.counts ?? {};

  const download = async () => {
    try {
      const url = URL.createObjectURL(await documentApi.exportChunks(documentId));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${documentId}-chunks.jsonl`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="space-y-2 rounded-2xl border border-border bg-card p-3 lg:sticky lg:top-6 lg:self-start">
        <p className="px-1 text-[11px] font-medium text-muted-foreground">Theo mục lục</p>
        {toc ? (
          <TocNav entries={toc.entries} perNode={counts.perNode ?? {}} selected={node} onSelect={setNode} />
        ) : (
          <p className="px-1 text-xs text-muted-foreground">Chưa có mục lục.</p>
        )}
      </aside>

      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Chips
            value={only}
            onChange={setOnly}
            options={[
              { value: "all", label: "Tất cả", count: counts.all },
              { value: "review", label: "Cần xem lại", count: counts.review },
            ]}
          />
          <div className="flex items-center gap-2">
            <SearchBox value={q} onChange={setQ} placeholder="Tìm trong nội dung..." className="w-52" />
            <Button variant="outline" size="sm" onClick={download}>
              <Download /> Tải xuống
            </Button>
          </div>
        </div>
        {data && (data.items ?? []).length === 0 ? (
          <EmptyState title="Không có đoạn nào phù hợp" />
        ) : (
          <div className="space-y-3">
            {(data?.items ?? []).map((c) => (
              <ChunkCard key={c.chunkId} c={c} onPreview={onPreview} previewPage={previewPage} />
            ))}
          </div>
        )}
        <Pager page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPage={setPage} />
      </div>
    </div>
  );
}

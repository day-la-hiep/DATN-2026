"use client";

import { useMutation } from "@tanstack/react-query";
import { Check, Pencil, Plus, RefreshCw, Trash2, Undo2, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { Chips, Pager, SearchBox, SectionCard, selectCls } from "./bits";
import { errorMessage, documentApi } from "../api";
import { LEVEL_TONE, LEVELS } from "../constants";
import { usePage, useRefreshDocument } from "../hooks";
import type { TocDoc, TocEntry, TocUpdate } from "../types";
import { PageChip } from "./PagePreview";

const PAGE_SIZE = 100;

function TitleCell({ entry, onSave }: { entry: TocEntry; onSave: (title: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [v, setV] = useState(entry.title);
  const indent = { paddingLeft: `${entry.level * 14}px` };
  if (!editing) {
    return (
      <div className="group/t flex min-w-0 items-center gap-1.5" style={indent}>
        <span className={cn("truncate text-xs", entry.level <= 1 && "font-semibold", LEVEL_TONE[entry.level])} title={entry.title}>
          {entry.title}
        </span>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setEditing(true);
          }}
          className="cursor-pointer text-muted-foreground opacity-0 transition-opacity group-hover/t:opacity-100 focus-visible:opacity-100"
          aria-label="Sửa tên"
        >
          <Pencil className="size-3" />
        </button>
      </div>
    );
  }
  const commit = () => {
    setEditing(false);
    if (v.trim() && v.trim() !== entry.title) onSave(v.trim());
    else setV(entry.title);
  };
  const cancel = () => {
    setEditing(false);
    setV(entry.title);
  };
  return (
    <div className="flex items-center gap-1" style={indent} onClick={(e) => e.stopPropagation()}>
      <Input
        autoFocus
        value={v}
        onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") cancel();
        }}
        className="h-7 rounded-lg px-2 text-xs"
      />
      <Button variant="ghost" size="icon-xs" onClick={commit} aria-label="Lưu">
        <Check />
      </Button>
      <Button variant="ghost" size="icon-xs" onClick={cancel} aria-label="Bỏ qua">
        <X />
      </Button>
    </div>
  );
}

function PageCell({ entry, onSave }: { entry: TocEntry; onSave: (page: number | null) => void }) {
  const orig = entry.page_printed == null ? "" : String(entry.page_printed);
  const [v, setV] = useState(orig);
  const commit = () => {
    if (v !== orig) onSave(v.trim() === "" ? null : parseInt(v, 10));
  };
  return (
    <Input
      value={v}
      onChange={(e) => setV(e.target.value.replace(/\D/g, ""))}
      onBlur={commit}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.key === "Enter" && commit()}
      inputMode="numeric"
      className={cn("h-7 w-16 rounded-lg px-2 text-right font-mono text-xs", entry.suspect && "border-amber-500/60 bg-amber-500/10")}
      aria-label={`Trang in của ${entry.title}`}
    />
  );
}

function AddDialog({
  open,
  after,
  onOpenChange,
  onAdd,
}: {
  open: boolean;
  after: TocEntry | null;
  onOpenChange: (o: boolean) => void;
  onAdd: (e: { title: string; level: number; page_printed?: number; after_id?: string }) => void;
}) {
  const [title, setTitle] = useState("");
  const [level, setLevel] = useState(2);
  const [page, setPage] = useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Thêm mục vào mục lục</DialogTitle>
          <DialogDescription className="leading-relaxed">
            {after ? <>Chèn ngay sau “{after.title}”.</> : "Chèn vào cuối danh sách."} Dùng khi AI bỏ sót một dòng của mục lục.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <label className="block space-y-1">
            <span className="text-xs font-medium">Tên mục</span>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} className="h-9 rounded-xl text-sm" />
          </label>
          <div className="flex items-end gap-4">
            <label className="space-y-1">
              <span className="block text-xs font-medium">Cấp</span>
              <select value={level} onChange={(e) => setLevel(parseInt(e.target.value, 10))} className={cn(selectCls, "h-9")} aria-label="Cấp">
                {LEVELS.map((l) => (
                  <option key={l.v} value={l.v}>
                    {l.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="block text-xs font-medium">Trang in</span>
              <Input value={page} onChange={(e) => setPage(e.target.value.replace(/\D/g, ""))} inputMode="numeric" className="h-9 w-24 rounded-xl font-mono text-sm" />
            </label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Hủy
          </Button>
          <Button
            disabled={!title.trim()}
            onClick={() => {
              onAdd({ title: title.trim(), level, page_printed: page ? parseInt(page, 10) : undefined, after_id: after?.id });
              setTitle("");
              setPage("");
              onOpenChange(false);
            }}
          >
            Thêm
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OffsetCard({
  doc,
  pending,
  onSave,
  onRefresh,
}: {
  doc: TocDoc;
  pending: boolean;
  onSave: (offset: number | null) => void;
  onRefresh: () => void;
}) {
  const [v, setV] = useState(doc.offset == null ? "" : String(doc.offset));
  const info = doc.offset_info ?? {};
  const votes = Object.entries(info.votes ?? {});
  const total = doc.entries.filter((e) => !e.out_of_range && e.page != null).length;
  return (
    <SectionCard
      title="Số trang"
      description="Số trang in trong sách thường khác số trang của file PDF (do bìa, lời nói đầu…). Hệ thống tự tính độ chênh bằng cách đối chiếu tên mục với nội dung sách; nếu sai, bạn có thể nhập tay. Mục “đã định vị” là mục đã tìm thấy đúng dòng tiêu đề trong sách."
      action={
        <Button variant="outline" size="sm" disabled={pending} onClick={onRefresh} title="Tính lại độ chênh số trang, vd sau khi đã đọc xong nội dung sách">
          <RefreshCw className={cn(pending && "animate-spin")} /> Tính lại
        </Button>
      }
    >
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <Input
          value={v}
          onChange={(e) => setV(e.target.value.replace(/[^\d-]/g, ""))}
          inputMode="numeric"
          placeholder="chưa có"
          className="h-8 w-24 rounded-lg font-mono text-xs"
          aria-label="Độ chênh lệch số trang"
        />
        <Button variant="outline" size="sm" disabled={pending || v === "" || v === "-" || String(doc.offset ?? "") === v} onClick={() => onSave(parseInt(v, 10))}>
          Nhập tay
        </Button>
        {info.source === "user" && (
          <Button variant="ghost" size="sm" disabled={pending} onClick={() => onSave(null)}>
            <Undo2 /> Dùng giá trị tự tính
          </Button>
        )}
        <span className="text-muted-foreground">
          {doc.offset == null
            ? "Chưa xác định (cần đọc xong nội dung sách, hoặc nhập tay)."
            : info.source === "user"
              ? "Do bạn nhập."
              : `Tự tính: ${info.support ?? 0}/${info.matched ?? 0} mục cho cùng kết quả.`}
        </span>
        {doc.offset != null && total > 0 && (
          <span className="font-mono text-[11px] text-muted-foreground">
            đã định vị {doc.anchored}/{total} mục
          </span>
        )}
        {info.source === "auto" && votes.length > 1 && (
          <span className="font-mono text-[11px] text-muted-foreground" title="chênh lệch: số mục ủng hộ">
            các kết quả: {votes.map(([k, n]) => `${k}:${n}`).join(", ")}
          </span>
        )}
      </div>
    </SectionCard>
  );
}

export function TocEditor({
  documentId,
  doc,
  selectedId,
  onSelect,
  onPreview,
}: {
  documentId: string;
  doc: TocDoc;
  selectedId: string | null;
  onSelect: (e: TocEntry) => void;
  onPreview: (page: number) => void;
}) {
  const refresh = useRefreshDocument(documentId);
  const [filter, setFilter] = useState("");
  const [q, setQ] = useState("");
  const [add, setAdd] = useState<{ open: boolean; entry: TocEntry | null }>({ open: false, entry: null });
  const [page, setPage] = usePage(`${filter}|${q}`);

  const update = useMutation({
    mutationFn: (body: TocUpdate) => documentApi.updateToc(documentId, body),
    onSuccess: (b) => refresh(b),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const recompute = useMutation({
    // áp lại override rỗng = chỉ tính lại độ lệch + neo từ dữ liệu trang hiện có
    mutationFn: () => documentApi.reapplyStage(documentId, "toc"),
    onSuccess: (b) => {
      refresh(b);
      toast.success("Đã đối chiếu lại số trang.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const pending = update.isPending || recompute.isPending;

  const all = doc.entries;
  const unanchored = (e: TocEntry) => !e.anchored && e.page != null && !e.out_of_range;
  const shown = all.filter((e) => {
    if (filter === "suspect" && !e.suspect) return false;
    if (filter === "unanchored" && !unanchored(e)) return false;
    if (filter === "structure" && e.level > 1) return false;
    return !q || e.title.toLowerCase().includes(q.toLowerCase());
  });
  const pageItems = shown.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const count = (f: (e: TocEntry) => boolean) => all.filter(f).length;

  return (
    <div className="space-y-4">
      {doc.warnings.map((w) => (
        <Alert key={w}>
          <AlertDescription className="text-xs">{w}</AlertDescription>
        </Alert>
      ))}

      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-muted-foreground">Trang mục lục ({doc.pages_source === "user" ? "bạn nhập" : "AI tìm"}):</span>
        {doc.toc_pages.slice(0, 24).map((p) => (
          <PageChip key={p} page={p} onOpen={onPreview} />
        ))}
        {doc.toc_pages.length > 24 && <span className="text-muted-foreground">… {doc.toc_pages.length} trang</span>}
      </div>

      <OffsetCard
        key={`${doc.offset}|${doc.offset_info?.source}`}
        doc={doc}
        pending={pending}
        onSave={(o) => update.mutate(o == null ? { clear_offset: true } : { offset: o })}
        onRefresh={() => recompute.mutate()}
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Chips
          value={filter}
          onChange={setFilter}
          options={[
            { value: "", label: "Tất cả", count: all.length },
            { value: "structure", label: "Phần + chương", count: count((e) => e.level <= 1) },
            { value: "suspect", label: "Cần kiểm tra", count: count((e) => Boolean(e.suspect)) },
            { value: "unanchored", label: "Chưa định vị", count: count(unanchored) },
          ]}
        />
        <div className="flex items-center gap-2">
          <SearchBox value={q} onChange={setQ} placeholder="Tìm tên mục..." className="w-48" />
          <Button variant="outline" size="sm" onClick={() => setAdd({ open: true, entry: null })}>
            <Plus /> Thêm
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-border bg-card">
        <table className="w-full min-w-[44rem] text-left">
          <thead className="border-b border-border bg-muted/40 text-[11px] font-medium text-muted-foreground">
            <tr>
              <th className="w-28 px-3 py-2">Cấp</th>
              <th className="px-2 py-2">Tên mục</th>
              <th className="w-20 px-2 py-2 text-right">Trang in</th>
              <th className="w-40 px-2 py-2">Trang trong file</th>
              <th className="w-24 px-2 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border/70">
            {pageItems.map((e) => (
              <tr
                key={e.id}
                onClick={() => onSelect(e)}
                className={cn(
                  "cursor-pointer transition-colors hover:bg-muted/30",
                  e.suspect && "bg-amber-500/[0.07]",
                  e.edited && "bg-brand/[0.04]",
                  selectedId === e.id && "bg-brand/10 hover:bg-brand/10"
                )}
              >
                <td className="px-3 py-1.5">
                  <select
                    value={e.level}
                    disabled={pending}
                    onClick={(ev) => ev.stopPropagation()}
                    onChange={(ev) => update.mutate({ items: [{ id: e.id, level: parseInt(ev.target.value, 10) }] })}
                    className={cn(selectCls, LEVEL_TONE[e.level])}
                    aria-label={`Cấp của ${e.title}`}
                  >
                    {LEVELS.map((l) => (
                      <option key={l.v} value={l.v} className="bg-popover text-foreground">
                        {l.label}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="max-w-md px-2 py-1.5">
                  <TitleCell key={e.title} entry={e} onSave={(title) => update.mutate({ items: [{ id: e.id, title }] })} />
                  {e.suspect && <p className="mt-0.5 truncate pl-0.5 text-[10px] text-amber-600 dark:text-amber-400" style={{ paddingLeft: `${e.level * 14}px` }}>{e.suspect_reason}</p>}
                </td>
                <td className="px-2 py-1.5 text-right">
                  <PageCell
                    key={String(e.page_printed)}
                    entry={e}
                    onSave={(p) => update.mutate({ items: [{ id: e.id, ...(p == null ? { clear_page: true } : { page_printed: p }) }] })}
                  />
                </td>
                <td className="px-2 py-1.5 text-xs">
                  {e.out_of_range ? (
                    <span className="text-[11px] text-muted-foreground" title={`Tương ứng trang ${e.page}, vượt quá số trang của file PDF này`}>
                      ngoài file này
                    </span>
                  ) : e.page != null ? (
                    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
                      <PageChip page={e.page} onOpen={onPreview} active={selectedId === e.id} />
                      <span
                        className={cn("text-[10px]", e.anchored ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400")}
                        title={e.anchored ? "Đã tìm thấy đúng dòng tiêu đề của mục ở trang này" : "Chỉ biết số trang theo mục lục, chưa tìm thấy dòng tiêu đề (vị trí bắt đầu mục chỉ chính xác đến trang)"}
                      >
                        {e.anchored ? "đã định vị" : "chưa định vị"}
                      </span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-2 py-1.5">
                  <div className="flex items-center justify-end gap-0.5" onClick={(ev) => ev.stopPropagation()}>
                    <Button variant="ghost" size="icon-xs" onClick={() => setAdd({ open: true, entry: e })} title="Thêm mục ngay sau mục này" aria-label="Thêm mục sau">
                      <Plus />
                    </Button>
                    {e.edited && !e.added && (
                      <Button variant="ghost" size="icon-xs" disabled={pending} onClick={() => update.mutate({ revert: [e.id] })} title="Quay về kết quả AI đọc ban đầu" aria-label="Quay về kết quả AI đọc ban đầu">
                        <Undo2 />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      disabled={pending}
                      onClick={() => update.mutate(e.added ? { removed_added: [e.id] } : { deleted: [e.id] })}
                      title="Xóa mục"
                      aria-label="Xóa mục"
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {pageItems.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-xs text-muted-foreground">
                  Không có mục nào phù hợp.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Pager page={page} pageSize={PAGE_SIZE} total={shown.length} onPage={setPage} />

      <AddDialog
        key={add.entry?.id ?? "end"}
        open={add.open}
        after={add.entry}
        onOpenChange={(o) => setAdd((s) => ({ ...s, open: o }))}
        onAdd={(e) => update.mutate({ added: [e] })}
      />
    </div>
  );
}

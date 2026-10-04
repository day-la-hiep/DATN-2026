"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookOpen, FileUp, Loader2, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatBytes } from "@/lib/utils";
import { ConfirmDialog } from "@/features/document-pipeline/components/ConfirmDialog";
import { EmptyState, StateBadge } from "@/features/document-pipeline/components/bits";
import { errorMessage, documentApi } from "@/features/document-pipeline/api";
import { STEP_INFO, STEP_ORDER } from "@/features/document-pipeline/constants";
import { qk, useDocuments } from "@/features/document-pipeline/hooks";
import type { DocumentSummary, StageState } from "@/features/document-pipeline/types";

const selectBox =
  "h-9 w-full cursor-pointer rounded-xl border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

function overall(states: DocumentSummary["states"]): StageState {
  const list = STEP_ORDER.map((s) => states[s] ?? "not_started");
  if (list.includes("running")) return "running";
  if (list.includes("failed")) return "failed";
  if (list.includes("pending_review")) return "pending_review";
  if (list.includes("stale")) return "stale";
  if (list.every((s) => s === "approved")) return "approved";
  return list.every((s) => s === "not_started") ? "not_started" : "pending_review";
}

const BAR: Partial<Record<StageState, string>> = {
  approved: "bg-emerald-500",
  running: "animate-pulse bg-brand",
  pending_review: "bg-amber-500",
  failed: "bg-red-500",
  stale: "bg-orange-400",
};

function DocumentCard({ document, onDelete }: { document: DocumentSummary; onDelete: () => void }) {
  const state = overall(document.states);
  const done = STEP_ORDER.filter((s) => document.states[s] === "approved").length;
  return (
    <div className="group relative flex flex-col gap-4 rounded-2xl border border-border bg-card p-5 transition-colors hover:border-brand/40">
      <Link href={`/admin/documents/${encodeURIComponent(document.id)}`} className="absolute inset-0 rounded-2xl" aria-label={`Mở ${document.title}`} />
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand">
          <BookOpen className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold tracking-tight text-foreground">{document.title}</h2>
          <p className="truncate font-mono text-[11px] text-muted-foreground">
            {document.id}
          </p>
        </div>
        <Button variant="ghost" size="icon-xs" className="relative z-10 text-muted-foreground hover:text-destructive" onClick={onDelete} aria-label="Xóa sách">
          <Trash2 />
        </Button>
      </div>
      <div className="space-y-2">
        <div className="flex gap-1">
          {STEP_ORDER.map((s) => (
            <span
              key={s}
              title={`${STEP_INFO[s].label}: ${document.states[s] ?? "not_started"}`}
              className={cn("h-1.5 flex-1 rounded-full bg-muted", BAR[document.states[s] ?? "not_started"])}
            />
          ))}
        </div>
        <div className="flex items-center justify-between gap-2">
          <StateBadge state={state} />
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
            {done}/{STEP_ORDER.length} bước hoàn tất
          </span>
        </div>
      </div>
    </div>
  );
}

function CreateDocumentDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [engine, setEngine] = useState("pdftotext");

  const create = useMutation({
    mutationFn: () => documentApi.createDocument({ file: file as File, title, engine }),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: qk.documents });
      toast.success(`Đã tạo sách “${b.title}”.`);
      onOpenChange(false);
      router.push(`/admin/documents/${encodeURIComponent(b.id)}`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Thêm sách mới</DialogTitle>
          <DialogDescription className="leading-relaxed">Tải lên file PDF của sách. Hệ thống sẽ đọc nội dung, đọc mục lục rồi chia sách thành các đoạn có ghi rõ nguồn. Bạn xác nhận kết quả sau từng bước.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="flex w-full cursor-pointer flex-col items-center gap-2 rounded-2xl border border-dashed border-border bg-muted/30 px-4 py-8 text-center transition-colors hover:border-brand/40 hover:bg-brand/5"
          >
            <FileUp className="size-6 text-muted-foreground" />
            {file ? (
              <span className="text-sm font-medium text-foreground">
                {file.name} <span className="font-normal text-muted-foreground">· {formatBytes(file.size)}</span>
              </span>
            ) : (
              <span className="text-sm text-muted-foreground">Chọn file PDF của sách</span>
            )}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              if (f && !title) setTitle(f.name.replace(/\.pdf$/i, ""));
            }}
          />
          <label className="block space-y-1">
            <span className="text-xs font-medium text-foreground">Tên sách</span>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} className="h-9 rounded-xl text-sm" />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-foreground">Cách đọc PDF</span>
            <select value={engine} onChange={(e) => setEngine(e.target.value)} className={selectBox}>
              <option value="pdftotext">Văn bản có sẵn (nhanh)</option>
              <option value="docling">Nhận dạng chữ từ ảnh (chậm)</option>
            </select>
          </label>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Chọn “nhận dạng chữ từ ảnh” khi PDF là bản scan hoặc chữ bị vỡ, sai dấu. Có thể đổi lại trong Cài đặt.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={create.isPending}>
            Hủy
          </Button>
          <Button onClick={() => create.mutate()} disabled={!file || !title.trim() || create.isPending}>
            {create.isPending && <Loader2 className="animate-spin" />}
            {create.isPending ? "Đang tải lên..." : "Thêm sách"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function TocDocumentsPage() {
  const books = useDocuments();
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<DocumentSummary | null>(null);

  const remove = useMutation({
    mutationFn: (id: string) => documentApi.deleteDocument(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.documents });
      toast.success("Đã xóa sách.");
      setDeleting(null);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const actions = (
    <div className="flex flex-wrap gap-2">
      <Button onClick={() => setCreating(true)}>
        <Plus /> Thêm sách
      </Button>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="font-serif text-2xl font-bold tracking-tight text-foreground">Số hóa sách giáo khoa</h1>
          <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
            Biến sách giáo khoa dạng PDF thành các đoạn nội dung có ghi rõ nguồn (phần, chương, bài, số trang), làm nền tri thức cho trợ lý AI. Cấu trúc sách được lấy từ chính mục lục của sách, và bạn kiểm tra, xác nhận từng bước.
          </p>
        </div>
        {actions}
      </div>

      {books.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-36 rounded-2xl" />
          ))}
        </div>
      ) : books.isError ? (
        <EmptyState title="Không tải được danh sách sách" hint={errorMessage(books.error)} action={<Button variant="outline" onClick={() => books.refetch()}>Thử lại</Button>} />
      ) : books.data && books.data.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {books.data.map((b) => (
            <DocumentCard key={b.id} document={b} onDelete={() => setDeleting(b)} />
          ))}
        </div>
      ) : (
        <EmptyState title="Chưa có sách nào" hint="Thêm sách bằng file PDF để bắt đầu." action={actions} />
      )}

      <CreateDocumentDialog key={`c-${creating}`} open={creating} onOpenChange={setCreating} />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Xóa “${deleting?.title ?? ""}”?`}
        description="Xóa toàn bộ file PDF, nội dung đã đọc, mục lục, các đoạn đã chia và chỉnh sửa của sách này. Không thể hoàn tác."
        confirmLabel="Xóa sách"
        destructive
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
      />
    </div>
  );
}

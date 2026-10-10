"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { HintIcon } from "@/components/ui/hint";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { errorMessage, documentApi } from "../api";
import { useRefreshDocument } from "../hooks";
import type { Settings } from "../types";

const selectBox =
  "h-9 w-full cursor-pointer rounded-xl border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="flex items-center gap-1 text-xs font-medium text-foreground">
        {label}
        {hint && <HintIcon content={hint} />}
      </span>
      {children}
    </label>
  );
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-0.5">
        <p className="flex items-center gap-1 text-xs font-medium text-foreground">
          {label}
          {hint && <HintIcon content={hint} />}
        </p>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
    </div>
  );
}

function Form({ documentId, initial, onClose }: { documentId: string; initial: Settings; onClose: () => void }) {
  const refresh = useRefreshDocument(documentId);
  const [s, setS] = useState<Settings>(initial);
  const [noise, setNoise] = useState(initial.noise_pages.join(", "));
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setS((p) => ({ ...p, [k]: v }));
  const num = (k: "max_tokens" | "min_tokens", v: string) => set(k, v === "" ? 0 : parseInt(v.replace(/\D/g, ""), 10) || 0);

  const save = useMutation({
    mutationFn: () => documentApi.saveSettings(documentId, { ...s, noise_pages: noise.split(",").map((x) => x.trim()).filter(Boolean) }),
    onSuccess: () => {
      refresh();
      toast.success("Đã lưu cài đặt.");
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
        <Field label="Tên sách">
          <Input value={s.title} onChange={(e) => set("title", e.target.value)} className="h-9 rounded-xl text-sm" />
        </Field>
        <div className="space-y-3 rounded-xl border border-border p-3">
          <p className="text-xs font-semibold text-foreground">Đọc nội dung</p>
          <Field label="Cách đọc" hint="Văn bản có sẵn: nhanh, dùng khi PDF có chữ tốt. Nhận dạng từ ảnh: chậm hơn. Chọn “nhận dạng từ ảnh” cho sách scan hoặc khi chữ trong PDF bị vỡ, sai dấu (chậm hơn). ">
            <select value={s.engine} onChange={(e) => set("engine", e.target.value as Settings["engine"])} className={selectBox}>
              <option value="pdftotext">Văn bản có sẵn</option>
              <option value="docling">Nhận dạng từ ảnh</option>
            </select>
          </Field>
          {s.engine === "docling" && (
            <>
              <Toggle label="Luôn đọc từ ảnh" hint="Bỏ qua văn bản ẩn sẵn có trong PDF (thường bị lỗi ở sách scan)." checked={s.docling_force_ocr} onChange={(v) => set("docling_force_ocr", v)} />
              <Toggle label="Nhận biết bảng" hint="Giữ đúng cột/hàng của bảng, kể cả mục lục dạng bảng; chậm hơn." checked={s.docling_tables} onChange={(v) => set("docling_tables", v)} />
            </>
          )}
          <Field label="Trang không dùng" hint="Các trang không đưa vào nội dung, cách nhau dấu phẩy, vd 1-30, 937-968 (chỉ mục cuối sách).">
            <Input value={noise} onChange={(e) => setNoise(e.target.value)} className="h-9 rounded-xl font-mono text-sm" placeholder="1-30, 937-968" />
          </Field>
        </div>
        <div className="space-y-3 rounded-xl border border-border p-3">
          <p className="text-xs font-semibold text-foreground">Mục lục</p>
          <Toggle label="Dùng AI" hint="Nếu tắt, hệ thống không thể tự đọc mục lục." checked={s.llm_enabled} onChange={(v) => set("llm_enabled", v)} />
          <Field label="Mô hình AI" hint="Để trống để dùng mô hình mặc định của hệ thống.">
            <Input value={s.llm_model} onChange={(e) => set("llm_model", e.target.value)} className="h-9 rounded-xl font-mono text-sm" placeholder="vd deepseek-v4-flash" />
          </Field>
        </div>
        <div className="space-y-3 rounded-xl border border-border p-3">
          <p className="text-xs font-semibold text-foreground">Chia đoạn</p>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Đoạn dài nhất" hint="Đơn vị ước lượng; 400 tương đương khoảng 300 từ.">
              <Input value={String(s.max_tokens)} onChange={(e) => num("max_tokens", e.target.value)} inputMode="numeric" className="h-9 rounded-xl font-mono text-sm" />
            </Field>
            <Field label="Đoạn ngắn nhất" hint="Đoạn ngắn hơn sẽ được đánh dấu “cần xem”.">
              <Input value={String(s.min_tokens)} onChange={(e) => num("min_tokens", e.target.value)} inputMode="numeric" className="h-9 rounded-xl font-mono text-sm" />
            </Field>
          </div>
          <Field label="Ranh giới đoạn" hint="Một đoạn không bao giờ chứa nội dung của hai mục khác nhau ở cấp được chọn. “Mọi mục” là khuyến nghị.">
            <select value={s.boundary_level} onChange={(e) => set("boundary_level", parseInt(e.target.value, 10))} className={selectBox}>
              <option value={3}>Mọi mục</option>
              <option value={2}>Đến bài/bệnh</option>
              <option value={1}>Đến chương</option>
              <option value={0}>Phần</option>
            </select>
          </Field>
          <Toggle label="Kèm đường dẫn mục" hint="Vd “Phần I › Chương 1 › Mụn trứng cá”, giúp trợ lý AI hiểu ngữ cảnh của đoạn." checked={s.breadcrumb} onChange={(v) => set("breadcrumb", v)} />
        </div>
        <div className="space-y-3 rounded-xl border border-border p-3">
          <p className="text-xs font-semibold text-foreground">Tìm kiếm</p>
          <Field label="Ngôn ngữ" hint="“Việt xen Anh” là khuyến nghị. Quyết định cách xử lý chữ khi lưu vào kho tri thức: tiếng Việt tách từ ghép (vảy nến), tiếng Anh gộp số ít/số nhiều (treatments → treatment). Chọn “tiếng Anh” cho sách thuần Anh để lưu nhanh hơn. Đổi xong cần làm lại bước Lưu vào kho.">
            <select value={s.text_language} onChange={(e) => set("text_language", e.target.value as Settings["text_language"])} className={selectBox}>
              <option value="mixed">Việt xen Anh</option>
              <option value="vi">Việt</option>
              <option value="en">Anh</option>
            </select>
          </Field>
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose} disabled={save.isPending}>
          Hủy
        </Button>
        <Button
          onClick={() => save.mutate()}
          disabled={save.isPending || !s.title.trim() || s.max_tokens < 50 || s.max_tokens > 4000 || s.min_tokens > 1000}
          className={cn(save.isPending && "opacity-80")}
        >
          {save.isPending && <Loader2 className="animate-spin" />} Lưu
        </Button>
      </DialogFooter>
    </>
  );
}

export function SettingsDialog({ documentId, open, onOpenChange }: { documentId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const q = useQuery({ queryKey: ["toc", documentId, "settings"], queryFn: () => documentApi.getSettings(documentId), enabled: open, staleTime: 0, gcTime: 0 });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Cài đặt sách</DialogTitle>
          <DialogDescription>Cần làm lại bước liên quan để áp dụng.</DialogDescription>
        </DialogHeader>
        {q.isLoading || !q.data ? (
          <p className="py-8 text-center text-xs text-muted-foreground">{q.isError ? errorMessage(q.error) : "Đang tải..."}</p>
        ) : (
          <Form documentId={documentId} initial={q.data} onClose={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}

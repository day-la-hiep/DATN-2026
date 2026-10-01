"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { errorMessage, tocApi } from "../api";
import { useRefreshBook } from "../hooks";
import type { Settings } from "../types";

const selectBox =
  "h-9 w-full cursor-pointer rounded-xl border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-foreground">{label}</span>
      {children}
      {hint && <span className="block text-[11px] leading-relaxed text-muted-foreground">{hint}</span>}
    </label>
  );
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-0.5">
        <p className="text-xs font-medium text-foreground">{label}</p>
        {hint && <p className="text-[11px] leading-relaxed text-muted-foreground">{hint}</p>}
      </div>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
    </div>
  );
}

function Form({ bookId, initial, onClose }: { bookId: string; initial: Settings; onClose: () => void }) {
  const refresh = useRefreshBook(bookId);
  const [s, setS] = useState<Settings>(initial);
  const [noise, setNoise] = useState(initial.noisePages.join(", "));
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setS((p) => ({ ...p, [k]: v }));
  const num = (k: "maxTokens" | "minTokens", v: string) => set(k, v === "" ? 0 : parseInt(v.replace(/\D/g, ""), 10) || 0);

  const save = useMutation({
    mutationFn: () => tocApi.saveSettings(bookId, { ...s, noisePages: noise.split(",").map((x) => x.trim()).filter(Boolean) }),
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
          <Field label="Cách đọc PDF" hint="Chọn “nhận dạng chữ từ ảnh” cho sách scan hoặc khi chữ trong PDF bị vỡ, sai dấu (chậm hơn). Nếu PDF có sẵn văn bản tốt, dùng văn bản có sẵn (nhanh).">
            <select value={s.engine} onChange={(e) => set("engine", e.target.value as Settings["engine"])} className={selectBox}>
              <option value="pdftotext">Văn bản có sẵn trong PDF (nhanh)</option>
              <option value="docling">Nhận dạng chữ từ ảnh trang (chậm)</option>
            </select>
          </Field>
          {s.engine === "docling" && (
            <>
              <Toggle label="Luôn đọc lại từ ảnh" hint="Bỏ qua văn bản ẩn sẵn có trong PDF (thường bị lỗi ở sách scan)." checked={s.doclingForceOcr} onChange={(v) => set("doclingForceOcr", v)} />
              <Toggle label="Nhận biết bảng" hint="Giữ đúng cột/hàng của bảng, kể cả mục lục dạng bảng; chậm hơn." checked={s.doclingTables} onChange={(v) => set("doclingTables", v)} />
            </>
          )}
          <Field label="Trang không dùng" hint="Các trang không đưa vào nội dung, cách nhau dấu phẩy, vd 1-30, 937-968 (chỉ mục cuối sách).">
            <Input value={noise} onChange={(e) => setNoise(e.target.value)} className="h-9 rounded-xl font-mono text-sm" placeholder="1-30, 937-968" />
          </Field>
        </div>
        <div className="space-y-3 rounded-xl border border-border p-3">
          <p className="text-xs font-semibold text-foreground">Đọc mục lục bằng AI</p>
          <Toggle label="Dùng AI đọc mục lục" hint="Nếu tắt, hệ thống không thể tự đọc mục lục." checked={s.llmEnabled} onChange={(v) => set("llmEnabled", v)} />
          <Field label="Mô hình AI (nâng cao)" hint="Để trống để dùng mô hình mặc định của hệ thống.">
            <Input value={s.llmModel} onChange={(e) => set("llmModel", e.target.value)} className="h-9 rounded-xl font-mono text-sm" placeholder="vd deepseek-v4-flash" />
          </Field>
        </div>
        <div className="space-y-3 rounded-xl border border-border p-3">
          <p className="text-xs font-semibold text-foreground">Chia đoạn</p>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Độ dài tối đa mỗi đoạn" hint="Đơn vị ước lượng; 400 tương đương khoảng 300 từ.">
              <Input value={String(s.maxTokens)} onChange={(e) => num("maxTokens", e.target.value)} inputMode="numeric" className="h-9 rounded-xl font-mono text-sm" />
            </Field>
            <Field label="Độ dài tối thiểu mỗi đoạn" hint="Đoạn ngắn hơn sẽ được đánh dấu “cần xem”.">
              <Input value={String(s.minTokens)} onChange={(e) => num("minTokens", e.target.value)} inputMode="numeric" className="h-9 rounded-xl font-mono text-sm" />
            </Field>
          </div>
          <Field label="Không gộp đoạn qua ranh giới" hint="Một đoạn không bao giờ chứa nội dung của hai mục khác nhau ở cấp này trở lên.">
            <select value={s.boundaryLevel} onChange={(e) => set("boundaryLevel", parseInt(e.target.value, 10))} className={selectBox}>
              <option value={3}>Mọi mục trong mục lục (khuyến nghị)</option>
              <option value={2}>Phần, chương và bài/bệnh (không tách mục nhỏ)</option>
              <option value={1}>Chỉ phần và chương (gộp các bài/bệnh trong cùng chương)</option>
              <option value={0}>Chỉ phần</option>
            </select>
          </Field>
          <Toggle label="Ghi kèm đường dẫn mục lục vào đoạn" hint="Vd “Phần I › Chương 1 › Mụn trứng cá”, giúp trợ lý AI hiểu ngữ cảnh của đoạn." checked={s.breadcrumb} onChange={(v) => set("breadcrumb", v)} />
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose} disabled={save.isPending}>
          Hủy
        </Button>
        <Button
          onClick={() => save.mutate()}
          disabled={save.isPending || !s.title.trim() || s.maxTokens < 50 || s.maxTokens > 4000 || s.minTokens > 1000}
          className={cn(save.isPending && "opacity-80")}
        >
          {save.isPending && <Loader2 className="animate-spin" />} Lưu
        </Button>
      </DialogFooter>
    </>
  );
}

export function SettingsDialog({ bookId, open, onOpenChange }: { bookId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const q = useQuery({ queryKey: ["toc", bookId, "settings"], queryFn: () => tocApi.getSettings(bookId), enabled: open, staleTime: 0, gcTime: 0 });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Cài đặt sách</DialogTitle>
          <DialogDescription className="leading-relaxed">
            Thay đổi cài đặt không tự làm lại các bước đã xong. Hãy làm lại bước liên quan để áp dụng (đổi cách chia đoạn chỉ cần làm lại bước Chia đoạn).
          </DialogDescription>
        </DialogHeader>
        {q.isLoading || !q.data ? (
          <p className="py-8 text-center text-xs text-muted-foreground">{q.isError ? errorMessage(q.error) : "Đang tải..."}</p>
        ) : (
          <Form bookId={bookId} initial={q.data} onClose={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}

"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { STEP_INFO } from "../constants";
import type { Stage } from "../types";

interface Field {
  key: string;
  label: string;
  placeholder: string;
  hint: string;
}

const FIELDS: Partial<Record<Stage["stage_id"], Field>> = {
  ingest: {
    key: "pages",
    label: "Khoảng trang cần đọc (không bắt buộc)",
    placeholder: "vd 1-300",
    hint: "Chỉ áp dụng khi nhận dạng chữ từ ảnh. Để trống = đọc cả sách. Trang đã đọc ở lần trước không phải đọc lại.",
  },
  toc: {
    key: "pages",
    label: "Trang mục lục (không bắt buộc)",
    placeholder: "vd 8-22",
    hint: "Nếu biết mục lục nằm ở trang nào của file PDF thì nhập vào (vd 8-22). Để trống, AI sẽ tự tìm trong các trang đầu và cuối sách.",
  },
};

/** Hộp thoại tùy chọn trước khi chạy một bước. Bước không có tùy chọn (chunk) chạy thẳng, không mở hộp này. */
export function hasRunOptions(id: Stage["stage_id"]): boolean {
  return FIELDS[id] !== undefined;
}

export function RunDialog({
  stage,
  open,
  onOpenChange,
  pending,
  onRun,
}: {
  stage: Stage;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  pending?: boolean;
  onRun: (options: Record<string, unknown>) => void;
}) {
  const field = FIELDS[stage.stage_id];
  const [value, setValue] = useState(field ? String(stage.options?.[field.key] ?? "") : "");
  const info = STEP_INFO[stage.stage_id];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {stage.state === "not_started" ? "Bắt đầu" : "Làm lại"}: {info.label}
          </DialogTitle>
          <DialogDescription className="leading-relaxed">{info.desc}</DialogDescription>
        </DialogHeader>
        {field && (
          <label className="block space-y-1">
            <span className="text-xs font-medium text-foreground">{field.label}</span>
            <Input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={field.placeholder}
              className="h-9 rounded-xl font-mono text-sm"
              autoFocus
            />
            <span className="block text-[11px] leading-relaxed text-muted-foreground">{field.hint}</span>
          </label>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
            Hủy
          </Button>
          <Button
            disabled={pending}
            onClick={() => onRun(field && value.trim() ? { [field.key]: value.trim() } : {})}
          >
            {stage.state === "not_started" ? "Bắt đầu" : "Làm lại"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

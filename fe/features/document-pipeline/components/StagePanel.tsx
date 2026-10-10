"use client";

import { Ban, Check, ChevronDown, Play, RotateCcw, ScrollText } from "lucide-react";
import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Hint, HintIcon } from "@/components/ui/hint";
import { cn } from "@/lib/utils";
import { KeyValueGrid, StateBadge } from "./bits";
import { STEP_INFO } from "../constants";
import type { Stage } from "../types";

const SUMMARY_LABELS: Record<string, string> = {
  engine: "Cách đọc",
  pages: "Số trang",
  page_range: "Khoảng trang",
  pages_skipped: "Trang không dùng",
  pages_empty: "Trang trống",
  pages_high_noise: "Trang nghi lỗi chữ",
  figures: "Số hình ảnh",
  toc_pages: "Trang mục lục",
  pages_source: "Nguồn trang mục lục",
  entries: "Số mục",
  parts: "Số phần",
  sections: "Số chương",
  topics: "Số bài/bệnh",
  suspect: "Mục cần kiểm tra",
  offset: "Chênh lệch số trang",
  anchored: "Mục đã định vị",
  chunks: "Số đoạn",
  tokens: "Độ dài đoạn (ngắn / giữa / dài)",
  toc_entries_used: "Mục có nội dung",
  toc_entries_total: "Tổng số mục",
  boundary_chunks: "Đoạn có vị trí chưa chắc",
  suspect_chunks: "Đoạn thuộc mục cần kiểm tra",
  too_short: "Đoạn quá ngắn",
  too_long: "Đoạn quá dài",
  outside_toc_lines: "Dòng chữ ngoài mục lục",
  points: "Số đoạn đã lưu",
  collection: "Kho lưu trữ",
  embedding_model: "Mô hình tạo vector",
  dimension: "Số chiều vector",
};

/** Summary của backend -> cặp nhãn tiếng Việt/giá trị dễ đọc; bỏ số liệu kỹ thuật (llm). */
function readableSummary(summary: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(summary)) {
    if (k === "warnings" || k === "llm") continue;
    let val = v;
    if (k === "tokens" && v && typeof v === "object") {
      const t = v as { min?: number; median?: number; max?: number };
      val = `${t.min} / ${t.median} / ${t.max}`;
    } else if (k === "page_range" && Array.isArray(v)) val = v.join("–");
    else if (k === "pages_source") val = v === "user" ? "bạn nhập" : "AI tìm";
    else if (k === "engine") val = v === "docling" ? "nhận dạng từ ảnh" : "văn bản có sẵn";
    out[SUMMARY_LABELS[k] ?? k] = val;
  }
  return out;
}

function fmt(iso?: string | null) {
  if (!iso) return null;
  return new Date(iso).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

/** Điều khiển một bước: trạng thái, tiến độ, kết quả tóm tắt, chạy / hủy / duyệt / log. Nội dung duyệt đặt ở dưới (children). */
export function StagePanel({
  stage,
  busy,
  anotherRunning,
  onRun,
  onCancel,
  onApprove,
  onLog,
  onNext,
}: {
  stage: Stage;
  busy: boolean;
  anotherRunning: boolean;
  onRun: () => void;
  onCancel: () => void;
  onApprove: () => void;
  onLog: () => void;
  /** nhảy sang bước kế tiếp (hiện sau khi duyệt) */
  onNext?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const info = STEP_INFO[stage.stage_id];
  const running = stage.state === "running";
  const pct = stage.progress && stage.progress.total > 0 ? Math.round((stage.progress.done / stage.progress.total) * 100) : 0;
  const canApprove = stage.state === "pending_review";
  const hasResult = ["pending_review", "approved", "stale"].includes(stage.state);
  const warnings = Array.isArray(stage.summary?.warnings) ? (stage.summary.warnings as string[]) : [];
  const summary = readableSummary(stage.summary ?? {});
  const fresh = !hasResult && !running && stage.state !== "failed";

  return (
    <section
      className={cn(
        "rounded-2xl border bg-card p-4 sm:p-5",
        running ? "border-brand/40 shadow-sm shadow-brand/10" : canApprove ? "border-amber-500/40" : "border-border"
      )}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="flex items-center gap-1 text-sm font-semibold tracking-tight text-foreground">
          {info.label}
          <HintIcon
            content={
              <div className="space-y-1">
                <p>{info.desc}</p>
                {info.note && <p className="text-muted-foreground">{info.note}</p>}
              </div>
            }
          />
        </h2>
        <StateBadge state={stage.state} />
        {stage.uses_llm && (
          <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-muted-foreground">LLM</span>
        )}
        {stage.finished_at && !running && <span className="text-[11px] text-muted-foreground">{fmt(stage.finished_at)}</span>}
      </div>

      <div className="mt-3 space-y-3">
        {running && (
          <div className="space-y-1.5">
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className={cn("h-full rounded-full bg-brand transition-all", pct === 0 && "w-1/5 animate-pulse")}
                style={pct > 0 ? { width: `${pct}%` } : undefined}
              />
            </div>
            <p className="text-[11px] text-muted-foreground">
              {stage.progress?.message}
              {stage.progress && stage.progress.total > 0 && (
                <span className="ml-1.5 font-mono tabular-nums">
                  {stage.progress.done}/{stage.progress.total}
                </span>
              )}
            </p>
          </div>
        )}
        {stage.state === "failed" && stage.error && (
          <Alert variant="destructive">
            <AlertDescription className="text-xs leading-relaxed">{stage.error}</AlertDescription>
          </Alert>
        )}
        {stage.state === "stale" && (
          <Hint content="Bước trước đó vừa được thay đổi nên kết quả ở đây đã cũ. Hãy làm lại bước này.">
            <p className="w-fit text-xs text-orange-600 dark:text-orange-400">Kết quả đã cũ, cần làm lại</p>
          </Hint>
        )}
        {canApprove && (
          <Hint content={info.review}>
            <p className="w-fit text-xs text-amber-700 dark:text-amber-400">Cần bạn kiểm tra và xác nhận</p>
          </Hint>
        )}
        {stage.blocked_by.length > 0 && fresh && (
          <p className="text-xs text-muted-foreground">
            Chờ xác nhận: {stage.blocked_by.map((b) => STEP_INFO[b].label).join(", ")}.
          </p>
        )}
        {warnings.length > 0 && (
          <ul className="list-disc space-y-1 rounded-xl bg-amber-500/10 p-3 pl-7 text-xs leading-relaxed text-amber-700 dark:text-amber-400">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
        {hasResult && Object.keys(summary).length > 0 && (
          <div>
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="flex cursor-pointer items-center gap-1 text-[11px] font-medium text-muted-foreground hover:text-foreground"
            >
              <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
              Kết quả
            </button>
            {open && (
              <div className="mt-2 rounded-xl bg-muted/50 p-3">
                <KeyValueGrid data={summary} />
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {running ? (
            <Hint content="Dừng bước đang chạy. Có thể chạy lại sau.">
              <span>
                <Button variant="outline" size="sm" onClick={onCancel} disabled={busy}>
                  <Ban /> Dừng
                </Button>
              </span>
            </Hint>
          ) : (
            <Hint
              content={
                stage.blocked_by.length > 0
                  ? "Cần xác nhận bước trước trước khi chạy bước này."
                  : anotherRunning
                    ? "Đang có bước khác chạy, chờ bước đó xong."
                    : fresh
                      ? "Chạy bước này lần đầu."
                      : "Chạy lại bước này và thay thế kết quả hiện tại."
              }
            >
              <span>
                <Button
                  variant={fresh || stage.state === "failed" ? "default" : "outline"}
                  size="sm"
                  onClick={onRun}
                  disabled={busy || anotherRunning || stage.blocked_by.length > 0}
                >
                  {fresh || stage.state === "failed" || stage.state === "cancelled" ? <Play /> : <RotateCcw />}
                  {fresh ? "Bắt đầu" : "Làm lại"}
                </Button>
              </span>
            </Hint>
          )}
          {canApprove && (
            <Hint content="Xác nhận kết quả đã đúng để mở bước tiếp theo.">
              <span>
                <Button size="sm" onClick={onApprove} disabled={busy} className="bg-emerald-600 bg-none hover:bg-emerald-700">
                  <Check /> Xác nhận
                </Button>
              </span>
            </Hint>
          )}
          {stage.state === "approved" && onNext && (
            <Button variant="ghost" size="sm" onClick={onNext}>
              Bước tiếp →
            </Button>
          )}
          {(stage.started_at || running) && (
            <Hint content="Xem nhật ký xử lý của bước này.">
              <Button variant="ghost" size="sm" onClick={onLog}>
                <ScrollText /> Nhật ký
              </Button>
            </Hint>
          )}
        </div>
      </div>
    </section>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { errorMessage, tocApi } from "../api";
import { STEP_INFO } from "../constants";
import type { StepId } from "../types";

export function StageLogDialog({
  bookId,
  stage,
  running,
  onClose,
}: {
  bookId: string;
  stage: StepId | null;
  running: boolean;
  onClose: () => void;
}) {
  const q = useQuery({
    queryKey: ["toc", bookId, "log", stage],
    queryFn: () => tocApi.stageLog(bookId, stage as StepId),
    enabled: stage !== null,
    refetchInterval: running ? 2000 : false,
  });
  return (
    <Dialog open={stage !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Nhật ký · {stage ? STEP_INFO[stage].label : ""}</DialogTitle>
          <DialogDescription>300 dòng gần nhất{running ? " (tự cập nhật)" : ""}.</DialogDescription>
        </DialogHeader>
        <pre className="max-h-[60vh] overflow-auto rounded-xl bg-muted p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words">
          {q.isError ? errorMessage(q.error) : q.data || (q.isLoading ? "Đang tải..." : "(chưa có nhật ký)")}
        </pre>
      </DialogContent>
    </Dialog>
  );
}

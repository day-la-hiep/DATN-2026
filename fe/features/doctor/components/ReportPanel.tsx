"use client";

import { Brain, CheckCircle2, FileText, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDoctorStore } from "../store";
import { STATUS_ACTION_CONFIG } from "../constants";
import { Hint } from "@/components/ui/hint";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PatientInfoCard } from "./PatientInfoCard";
import { ClinicalFactList } from "./ClinicalFactList";
import { AiSummaryView } from "./AiSummaryView";

export function ReportPanel() {
  const activeSessionId = useDoctorStore((s) => s.activeSessionId);
  const sessions = useDoctorStore((s) => s.sessions);
  const acceptSession = useDoctorStore((s) => s.acceptSession);
  const resolveSession = useDoctorStore((s) => s.resolveSession);
  const loading = useDoctorStore((s) => s.loading);
  const actionLoading = useDoctorStore((s) => s.actionLoading);

  const session = sessions.find((s) => s.id === activeSessionId);

  if (!activeSessionId || !session) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground p-6">
        <div className="text-center">
          <FileText className="size-10 mx-auto mb-3 opacity-30" />
          <p className="text-sm">Chọn một ca</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="p-4 space-y-4">
        <Skeleton className="h-6 w-2/3 rounded-lg" />
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-44 w-full rounded-xl" />
      </div>
    );
  }

  const actionCfg = STATUS_ACTION_CONFIG[session.status] ?? STATUS_ACTION_CONFIG.pending;
  const ActionIcon = actionCfg.icon;

  const reportTime = session.report?.createdAt ? new Date(session.report.createdAt).toLocaleString("vi-VN") : null;

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b border-border px-4 py-3">
        <Hint side="left" content={reportTime ? `Báo cáo AI tạo lúc ${reportTime}` : "Chưa có báo cáo AI cho ca này"}>
          <h3 className="w-fit font-serif text-lg font-bold tracking-tight text-foreground">Báo cáo</h3>
        </Hint>
        <PatientInfoCard patient={session.patient} reason={session.reason} />
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto pt-4">
        <ClinicalFactList facts={session.clinicalFacts ?? []} />
        {session.report ? (
          <AiSummaryView summary={session.report.summary} />
        ) : (
          <div className="px-4 py-8 text-center text-muted-foreground">
            <Brain className="mx-auto mb-2 size-7 opacity-30" />
            <p className="text-xs">Chưa có báo cáo</p>
          </div>
        )}
      </div>

      <div className="border-t border-border p-3">
        {actionCfg.action ? (
          <Hint side="top" content={actionCfg.hint}>
            <Button
              disabled={actionLoading}
              onClick={() => (actionCfg.action === "accept" ? acceptSession(session.id) : resolveSession(session.id))}
              className={cn("h-10 w-full rounded-xl text-sm font-medium transition-all active:scale-[0.98]", actionCfg.buttonClass)}
            >
              {actionLoading ? <Loader2 className="size-4 animate-spin" /> : <ActionIcon className="size-4" />}
              {actionLoading ? "Đang xử lý" : actionCfg.label}
            </Button>
          </Hint>
        ) : (
          <Hint side="top" content={session.resolvedAt ? `Đã đóng lúc ${new Date(session.resolvedAt).toLocaleString("vi-VN")}` : actionCfg.hint}>
            <p className="flex items-center justify-center gap-1.5 rounded-xl bg-muted/50 py-2.5 text-xs font-medium text-muted-foreground">
              <CheckCircle2 className="size-3.5" />
              {actionCfg.label}
            </p>
          </Hint>
        )}
      </div>
    </div>
  );
}

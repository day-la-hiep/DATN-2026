"use client";

import { Brain, CheckCircle2, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDoctorStore } from "../store";
import { STATUS_ACTION_CONFIG } from "../constants";
import { Badge } from "@/components/ui/badge";
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
          <p className="text-sm">Chọn một ca tư vấn để xem báo cáo AI</p>
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

  const actionCfg = STATUS_ACTION_CONFIG[session.status];
  const ActionIcon = actionCfg.icon;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-border px-4 py-3 bg-background/50 backdrop-blur-sm">
        <div className="flex items-center gap-2 mb-1">
          <div className="flex items-center justify-center size-6 rounded-lg bg-brand/10">
            <Brain className="size-3.5 text-brand" />
          </div>
          <h3 className="text-sm font-semibold text-foreground">
            Báo cáo AI kết luận
          </h3>
        </div>
        <p className="text-[10px] text-muted-foreground font-mono">
          PRE-CONSULTATION REPORT •{" "}
          {session.report
            ? new Date(session.report.createdAt).toLocaleString("vi-VN")
            : "Chưa có"}
        </p>
      </div>

      {/* Main Content Scroll Area */}
      <div className="flex-1 overflow-y-auto">
        {/* Patient overview card */}
        <div className="px-4 pt-4 pb-3">
          <PatientInfoCard patient={session.patient} reason={session.reason} />
        </div>

        {/* Structured Clinical Facts */}
        <ClinicalFactList facts={session.clinicalFacts} />

        {/* AI Markdown Summary */}
        {session.report ? (
          <AiSummaryView summary={session.report.summary} />
        ) : (
          <div className="px-4 py-8 text-center text-muted-foreground">
            <Brain className="size-8 mx-auto mb-2 opacity-30" />
            <p className="text-xs">Chưa có báo cáo AI cho phiên này</p>
          </div>
        )}
      </div>

      {/* Action Footer Button */}
      {actionCfg.action && (
        <div className="border-t border-border p-4 bg-background/50">
          <Button
            disabled={actionLoading}
            onClick={() =>
              actionCfg.action === "accept"
                ? acceptSession(session.id)
                : resolveSession(session.id)
            }
            className={cn(
              "w-full rounded-xl h-10 text-sm font-semibold transition-all shadow-sm",
              actionCfg.buttonClass
            )}
          >
            <ActionIcon className="size-4 mr-2" />
            {actionLoading ? "Đang xử lý..." : actionCfg.label}
          </Button>
        </div>
      )}

      {session.status === "resolved" && (
        <div className="border-t border-border p-4 bg-background/50">
          <Badge
            variant="outline"
            className="w-full justify-center py-2 rounded-xl text-xs font-medium border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400"
          >
            <CheckCircle2 className="size-3.5 mr-1.5" />
            Phiên đã hoàn tất •{" "}
            {session.resolvedAt
              ? new Date(session.resolvedAt).toLocaleString("vi-VN")
              : ""}
          </Badge>
        </div>
      )}
    </div>
  );
}

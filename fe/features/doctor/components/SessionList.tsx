"use client";

import { Inbox } from "lucide-react";
import { Hint } from "@/components/ui/hint";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatRelativeTime } from "@/lib/utils";
import { FILTER_OPTIONS, STATUS_CONFIG } from "../constants";
import { useDoctorStore } from "../store";
import type { ConsultationSession } from "../types";

function calculateAge(dob?: string): string {
  if (!dob) return "--";
  const birth = new Date(dob);
  if (isNaN(birth.getTime())) return "--";
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  const m = today.getMonth() - birth.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) age--;
  return age < 0 ? "--" : String(age);
}

function SessionRow({ session, active, onSelect }: { session: ConsultationSession; active: boolean; onSelect: (id: string) => void }) {
  const cfg = STATUS_CONFIG[session.status] ?? STATUS_CONFIG.pending;
  const gender = session.patient?.gender === "female" ? "Nữ" : "Nam";
  const facts = session.clinicalFacts?.length ?? 0;

  return (
    <Hint
      side="right"
      content={
        <div className="space-y-1">
          <p className="font-medium">{session.patient?.fullName ?? "Bệnh nhân"}</p>
          <p className="text-muted-foreground">{session.reason || "Chưa ghi lý do"}</p>
          <p className="text-muted-foreground">{cfg.hint}</p>
          {facts > 0 && <p className="text-muted-foreground">{facts} dữ kiện lâm sàng AI đã trích xuất</p>}
        </div>
      }
    >
      <button
        type="button"
        onClick={() => onSelect(session.id)}
        aria-current={active ? "true" : undefined}
        className={cn(
          "group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors",
          active ? "bg-brand/10" : "hover:bg-muted/60"
        )}
      >
        <span className={cn("size-2 shrink-0 rounded-full", cfg.dotClass, session.status === "pending" && "animate-pulse")} />
        <span className="min-w-0 flex-1">
          <span className={cn("block truncate text-sm", active ? "font-semibold text-brand" : "font-medium text-foreground")}>
            {session.patient?.fullName ?? "Bệnh nhân"}
          </span>
          <span className="block truncate text-[11px] text-muted-foreground">
            {gender}, {calculateAge(session.patient?.dob)}t · {formatRelativeTime(session.requestedAt)}
          </span>
        </span>
        {facts > 0 && (
          <span className="shrink-0 rounded-full bg-brand/10 px-1.5 py-0.5 font-mono text-[10px] font-medium text-brand">{facts}</span>
        )}
      </button>
    </Hint>
  );
}

export function SessionList() {
  const sessions = useDoctorStore((s) => s.sessions);
  const activeSessionId = useDoctorStore((s) => s.activeSessionId);
  const loading = useDoctorStore((s) => s.loading);
  const statusFilter = useDoctorStore((s) => s.statusFilter);
  const selectSession = useDoctorStore((s) => s.selectSession);
  const setStatusFilter = useDoctorStore((s) => s.setStatusFilter);

  const filtered = sessions.filter((s) => statusFilter === "all" || s.status === statusFilter);
  const count = (v: string) => (v === "all" ? sessions.length : sessions.filter((s) => s.status === v).length);

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b border-border px-4 py-3">
        <div className="flex items-baseline justify-between">
          <h2 className="font-serif text-lg font-bold tracking-tight text-foreground">Ca tư vấn</h2>
          <span className="font-mono text-xs text-muted-foreground">{filtered.length}</span>
        </div>
        <div className="grid grid-cols-4 gap-0.5 rounded-xl bg-muted p-0.5" role="tablist" aria-label="Lọc ca tư vấn">
          {FILTER_OPTIONS.map((opt) => {
            const on = statusFilter === opt.value;
            const full = opt.value === "all" ? "Tất cả ca tư vấn" : STATUS_CONFIG[opt.value].hint;
            return (
              <Hint key={opt.value} content={`${full} (${count(opt.value)})`}>
                <button
                  type="button"
                  role="tab"
                  aria-selected={on}
                  onClick={() => setStatusFilter(opt.value)}
                  className={cn(
                    "rounded-[10px] px-1 py-1 text-[11px] font-medium transition-all",
                    on ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {opt.label}
                </button>
              </Hint>
            );
          })}
        </div>
      </div>

      <div className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {loading ? (
          <div className="space-y-1 p-1">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-3 px-2 py-2">
                <Skeleton className="size-2 rounded-full" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3.5 w-3/4 rounded" />
                  <Skeleton className="h-2.5 w-1/2 rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center py-14 text-center text-muted-foreground">
            <Inbox className="mb-2 size-7 opacity-30" />
            <p className="text-xs">Chưa có ca</p>
          </div>
        ) : (
          filtered.map((s) => <SessionRow key={s.id} session={s} active={s.id === activeSessionId} onSelect={selectSession} />)
        )}
      </div>
    </div>
  );
}

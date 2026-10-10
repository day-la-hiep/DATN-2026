"use client";

import {
  User,
  Calendar,
  Filter,
  LogOut,
} from "lucide-react";
import { logout } from "@/features/auth/logout";
import { getAuthenticatedUser } from "@/services/client";
import { cn, formatRelativeTime } from "@/lib/utils";
import { useDoctorStore } from "../store";
import { STATUS_CONFIG, FILTER_OPTIONS } from "../constants";
import type { ConsultationSession, ConsultationStatus } from "../types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

function calculateAge(dob?: string): number | string {
  if (!dob) return "--";
  const birth = new Date(dob);
  if (isNaN(birth.getTime())) return "--";
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  const m = today.getMonth() - birth.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) age--;
  return isNaN(age) || age < 0 ? "--" : age;
}

interface SessionCardProps {
  session: ConsultationSession;
  isActive: boolean;
  onSelect: (id: string) => void;
}

function SessionCard({ session, isActive, onSelect }: SessionCardProps) {
  const cfg = STATUS_CONFIG[session.status] ?? STATUS_CONFIG.pending;
  const StatusIcon = cfg.icon;
  const age = calculateAge(session.patient?.dob);
  const factsCount = session.clinicalFacts?.length ?? 0;

  return (
    <div
      onClick={() => onSelect(session.id)}
      className={cn(
        "group relative flex flex-col gap-2 rounded-xl border p-3 cursor-pointer transition-all duration-150",
        isActive
          ? "border-brand bg-brand/5 shadow-xs"
          : "border-border/60 hover:border-border hover:bg-muted/40"
      )}
    >
      {/* Top row: Patient Name + Status */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-xs text-foreground truncate">
              {session.patient?.fullName ?? "Bệnh nhân"}
            </span>
            <span className="text-[11px] text-muted-foreground shrink-0 font-medium">
              ({session.patient?.gender === "female" ? "Nữ" : "Nam"}, {age}t)
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground line-clamp-1 mt-0.5">
            {session.reason}
          </p>
        </div>

        <Badge
          variant="outline"
          className={cn(
            "shrink-0 text-[10px] px-1.5 py-0.5 font-medium rounded-md flex items-center gap-1",
            cfg.badgeClass
          )}
        >
          <StatusIcon className="size-2.5" />
          {cfg.label}
        </Badge>
      </div>

      {/* Bottom meta row */}
      <div className="flex items-center justify-between text-[10px] text-muted-foreground/80 pt-1 border-t border-border/40 font-mono">
        <span className="flex items-center gap-1">
          <Calendar className="size-3" />
          {formatRelativeTime(session.requestedAt)}
        </span>
        {factsCount > 0 && (
          <span className="text-brand font-medium">
            {factsCount} dữ kiện AI
          </span>
        )}
      </div>
    </div>
  );
}

export function SessionList() {
  const sessions = useDoctorStore((s) => s.sessions);
  const activeSessionId = useDoctorStore((s) => s.activeSessionId);
  const loading = useDoctorStore((s) => s.loading);
  const statusFilter = useDoctorStore((s) => s.statusFilter);
  const selectSession = useDoctorStore((s) => s.selectSession);
  const setStatusFilter = useDoctorStore((s) => s.setStatusFilter);

  const account = getAuthenticatedUser();

  const filteredSessions = sessions.filter((s) => {
    if (statusFilter === "all") return true;
    return s.status === statusFilter;
  });

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-border px-4 py-3 bg-background/50 backdrop-blur-sm">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className="flex items-center justify-center size-6 rounded-lg bg-brand/10">
              <User className="size-3.5 text-brand" />
            </div>
            <h2 className="text-sm font-semibold text-foreground">
              Ca tư vấn trực tuyến
            </h2>
          </div>
          <span className="text-xs font-mono font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
            {filteredSessions.length}
          </span>
        </div>

        {/* Filter chips */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-none">
          <Filter className="size-3 text-muted-foreground shrink-0 mr-1" />
          {FILTER_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              size="sm"
              variant={statusFilter === opt.value ? "default" : "ghost"}
              onClick={() => setStatusFilter(opt.value)}
              className={cn(
                "h-6 px-2 text-[11px] rounded-lg font-medium transition-all",
                statusFilter === opt.value
                  ? "bg-brand text-brand-foreground shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {opt.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Session List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {loading ? (
          <div className="space-y-2.5 p-1">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="rounded-xl border border-border/60 p-3 space-y-2">
                <Skeleton className="h-4 w-3/4 rounded" />
                <Skeleton className="h-3 w-1/2 rounded" />
                <Skeleton className="h-2 w-1/4 rounded" />
              </div>
            ))}
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-center px-4">
            <User className="size-8 mb-2 opacity-30" />
            <p className="text-xs font-medium">Không có ca tư vấn nào</p>
            <p className="text-[11px] text-muted-foreground/70 mt-1">
              Thử chuyển bộ lọc sang &quot;Tất cả&quot;
            </p>
          </div>
        ) : (
          filteredSessions.map((session) => (
            <SessionCard
              key={session.id}
              session={session}
              isActive={session.id === activeSessionId}
              onSelect={selectSession}
            />
          ))
        )}
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-2.5">
        <span className="truncate text-xs font-medium text-foreground">
          {account?.full_name || account?.username || "Bác sĩ"}
        </span>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => void logout()}
          className="h-7 gap-1.5 px-2 text-[11px] text-muted-foreground hover:text-foreground"
        >
          <LogOut className="size-3.5" />
          Đăng xuất
        </Button>
      </div>
    </div>
  );
}

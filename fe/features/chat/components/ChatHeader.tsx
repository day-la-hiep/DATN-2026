"use client";

import { useState } from "react";
import { Menu, ShieldCheck, Sparkles, Stethoscope } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { doctorApi } from "@/features/doctor/api";
import { useChatStore } from "../store";

export function ChatHeader({ onOpenSidebar }: { onOpenSidebar: () => void }) {
  const activeId = useChatStore((s) => s.activeId);
  const conversations = useChatStore((s) => s.conversations);
  const streaming = useChatStore((s) =>
    activeId ? s.hasActiveStream(activeId) : false
  );
  const conversation = conversations.find((c) => c.id === activeId);
  const [requestingDoctor, setRequestingDoctor] = useState(false);

  const handleRequestDoctor = async () => {
    if (!activeId) return;
    try {
      setRequestingDoctor(true);
      await doctorApi.requestConsultation(activeId, "Bệnh nhân yêu cầu bác sĩ tư vấn trực tiếp");
      toast.success("Đã gửi yêu cầu kết nối Bác sĩ! AI đang tổng hợp báo cáo lâm sàng.");
    } catch {
      toast.error("Không thể gửi yêu cầu kết nối bác sĩ. Vui lòng thử lại.");
    } finally {
      setRequestingDoctor(false);
    }
  };

  return (
    <header className="border-b border-border/80 bg-background/80 backdrop-blur-md px-4 py-3 sticky top-0 z-20">
      <div className="mx-auto flex w-full max-w-4xl items-center gap-3">
        <Button
          variant="ghost"
          size="iconSm"
          onClick={onOpenSidebar}
          aria-label="Mở menu"
          className="lg:hidden rounded-lg text-muted-foreground hover:text-foreground"
        >
          <Menu className="size-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-sm font-semibold text-foreground tracking-tight">
            {conversation?.title || "Cuộc trò chuyện mới"}
          </h1>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
            {streaming ? (
              <span className="flex items-center gap-1.5 text-brand font-medium">
                <Sparkles className="size-3 animate-spin text-brand" />
                <span>Đang xử lý phân tích...</span>
              </span>
            ) : (
              <span className="flex items-center gap-1.5 font-sans">
                <span className="size-2 rounded-full bg-emerald-500 dark:bg-emerald-400 animate-pulse-subtle" />
                <span>Trực tuyến // Sẵn sàng</span>
              </span>
            )}
          </div>
        </div>

        {activeId && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleRequestDoctor}
            disabled={requestingDoctor}
            className="shrink-0 gap-1.5 rounded-full border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300 hover:bg-sky-500/20 text-xs font-medium"
            title="Gửi hồ sơ hội thoại và yêu cầu bác sĩ chuyên khoa tiếp quản"
          >
            <Stethoscope className="size-3.5 text-sky-600 dark:text-sky-400" />
            <span>{requestingDoctor ? "Đang kết nối..." : "Gặp Bác sĩ"}</span>
          </Button>
        )}

        <Badge variant="outline" className="shrink-0 gap-1.5 rounded-full border border-brand/20 bg-brand/5 px-3 py-1 font-mono text-xs font-medium text-brand">
          <ShieldCheck className="size-3.5 text-brand" />
          <span>Derma Clinical AI</span>
        </Badge>
      </div>
    </header>
  );
}

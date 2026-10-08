"use client";

import { useEffect } from "react";
import { useDoctorStore } from "../store";
import { SessionList } from "./SessionList";
import { ChatViewer } from "./ChatViewer";
import { ReportPanel } from "./ReportPanel";

export function DoctorConsultationPage() {
  const init = useDoctorStore((s) => s.init);

  useEffect(() => {
    init();
  }, [init]);

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      {/* Left Panel — Session List */}
      <aside className="hidden w-72 shrink-0 flex-col border-r border-border bg-sidebar/70 backdrop-blur-md lg:flex xl:w-80">
        <SessionList />
      </aside>

      {/* Center Panel — Chat Viewer */}
      <div className="flex min-w-0 flex-1 flex-col border-r border-border bg-background">
        <ChatViewer />
      </div>

      {/* Right Panel — AI Report */}
      <aside className="hidden w-80 shrink-0 flex-col bg-sidebar/50 backdrop-blur-md lg:flex xl:w-96">
        <ReportPanel />
      </aside>
    </div>
  );
}

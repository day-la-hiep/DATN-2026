"use client";

import { useState } from "react";
import { useChatStore } from "../store";
import { ChatSidebar } from "./ChatSidebar";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { QuestionModal } from "./QuestionModal";
import { SidebarProvider } from "@/components/ui/sidebar";

export function ChatPage() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const activeId = useChatStore((s) => s.activeId);
  const messages = useChatStore(
    (s) => (activeId ? s.messagesByConversation[activeId] : undefined)
  );
  const loadingMessages = useChatStore((s) => s.loadingMessages);

  return (
    <SidebarProvider open={!sidebarCollapsed} onOpenChange={(open) => setSidebarCollapsed(!open)} className="min-h-dvh flex-row">
      <div className="flex h-dvh w-full overflow-hidden bg-background">
        <ChatSidebar
          open={sidebarOpen}
          collapsed={sidebarCollapsed}
          onClose={() => setSidebarOpen(false)}
          onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
        />

        <div className="flex min-w-0 flex-1 flex-col bg-background">
          <main className="flex flex-1 flex-col overflow-hidden bg-background">
            <div className="flex flex-1 flex-col overflow-y-auto bg-background">
              <MessageList
                conversationId={activeId ?? ""}
                messages={messages ?? []}
                loading={loadingMessages}
              />
            </div>
            <div className="relative bg-background">
              {activeId && <QuestionModal conversationId={activeId} />}
              <ChatInput
                conversationId={activeId ?? undefined}
                onOpenSidebar={() => setSidebarOpen(true)}
              />
            </div>
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}

"use client";

import { useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  LogOut,
  Plus,
  Settings,
  Stethoscope,
  X,
} from "lucide-react";
import { CURRENT_USER, getInitials } from "@/features/user";
import { SettingsDialog } from "@/features/settings/components/SettingsDialog";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
} from "@/components/ui/sidebar";
import { useChatStore } from "../store";
import { cn, formatRelativeTime } from "@/lib/utils";

function SidebarInner({
  collapsed,
  onClose,
  onToggleCollapse,
  setSettingsOpen,
}: {
  collapsed: boolean;
  onClose: () => void;
  onToggleCollapse: () => void;
  setSettingsOpen: (open: boolean) => void;
}) {
  const conversations = useChatStore((s) => s.conversations);
  const activeId = useChatStore((s) => s.activeId);
  const loading = useChatStore((s) => s.loadingConversations);
  const startNewChat = useChatStore((s) => s.startNewChat);
  const selectConversation = useChatStore((s) => s.selectConversation);

  return (
    <Sidebar className="w-full h-full border-r border-border bg-sidebar/70 backdrop-blur-md overflow-hidden" collapsible="none">
      {/* Header sidebar */}
      <SidebarHeader className="p-0 py-3.5 border-b border-border overflow-hidden bg-background/50">
        <div className={cn("flex h-9 w-full items-center transition-all overflow-hidden", collapsed ? "justify-center px-0" : "justify-between px-3.5")}>
          <div className="flex items-center gap-2.5 min-w-0 overflow-hidden">
            {/* Logo da liễu */}
            <button
              type="button"
              onClick={collapsed ? onToggleCollapse : undefined}
              aria-label={collapsed ? "Mở rộng thanh bên" : "Trợ lý da liễu"}
              className={cn(
                "group/logo relative flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--brand)] to-[var(--brand-secondary,#4d7cff)] text-white shadow-xs transition-all outline-hidden cursor-pointer",
                collapsed ? "hover:shadow-accent hover:-translate-y-0.5" : "cursor-default"
              )}
            >
              <Stethoscope
                className={cn(
                  "size-4.5 transition-all duration-150",
                  collapsed && "group-hover/logo:scale-0 group-hover/logo:opacity-0"
                )}
              />
              {collapsed && (
                <ChevronRight className="absolute size-4.5 opacity-0 scale-0 transition-all duration-150 group-hover/logo:scale-100 group-hover/logo:opacity-100" />
              )}
            </button>

            {!collapsed && (
              <div className="flex flex-col min-w-0 leading-none">
                <span className="truncate text-sm font-serif font-normal text-foreground">
                  Derma AI
                </span>
                <span className="truncate font-mono text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">
                  Clinical Intelligence
                </span>
              </div>
            )}
          </div>

          {!collapsed && (
            <div className="flex items-center gap-1 shrink-0">
              <Button
                variant="ghost"
                size="iconSm"
                onClick={onClose}
                aria-label="Đóng menu"
                className="lg:hidden rounded-lg text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="iconSm"
                onClick={onToggleCollapse}
                aria-label="Thu gọn thanh bên"
                className="hidden text-muted-foreground lg:inline-flex rounded-lg hover:text-foreground"
              >
                <ChevronLeft className="size-4" />
              </Button>
            </div>
          )}
        </div>
      </SidebarHeader>

      {/* Tác vụ Cuộc trò chuyện mới */}
      <SidebarGroup className={cn("py-3 overflow-hidden transition-all border-b border-border/60", collapsed ? "px-0 flex justify-center" : "px-3")}>
        <SidebarMenu className="w-full">
          <SidebarMenuItem className="w-full flex justify-center">
            <SidebarMenuButton
              size="lg"
              onClick={() => {
                startNewChat();
                onClose();
              }}
              tooltip="Cuộc trò chuyện mới"
              className={cn(
                "rounded-xl bg-gradient-to-r from-[var(--brand)] to-[var(--brand-secondary,#4d7cff)] text-white font-medium text-xs shadow-xs transition-all hover:shadow-accent hover:-translate-y-0.5 active:scale-[0.98] overflow-hidden cursor-pointer",
                collapsed
                  ? "size-9 p-0 justify-center mx-auto"
                  : "w-full justify-start gap-2.5 px-3.5 py-2.5"
              )}
            >
              <Plus className="size-4 shrink-0" />
              {!collapsed && (
                <span className="whitespace-nowrap truncate text-xs font-semibold">
                  Cuộc trò chuyện mới
                </span>
              )}
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>

      {/* Nhãn nhóm */}
      {!collapsed && (
        <div className="px-3.5 pt-3 pb-1.5 flex items-center justify-between">
          <span className="font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-muted-foreground">
            Lịch sử tư vấn
          </span>
          <span className="size-1.5 rounded-full bg-brand/50" />
        </div>
      )}

      {/* Danh sách các cuộc trò chuyện */}
      {collapsed ? (
        <div className="flex-1" />
      ) : (
        <SidebarContent className="px-2.5 py-1 overflow-y-auto">
          <SidebarGroup className="p-0">
            <SidebarGroupContent>
              <SidebarMenu className="gap-1">
                {loading && conversations.length === 0 ? (
                  <div className="flex flex-col gap-1.5 p-1">
                    {[0, 1, 2].map((i) => (
                      <SidebarMenuSkeleton key={i} className="h-11 rounded-xl" />
                    ))}
                  </div>
                ) : (
                  conversations.map((conversation) => {
                    const isActive = activeId === conversation.id;
                    return (
                      <SidebarMenuItem key={conversation.id}>
                        <SidebarMenuButton
                          isActive={isActive}
                          onClick={() => {
                            selectConversation(conversation.id);
                            onClose();
                          }}
                          className={cn(
                            "h-auto w-full flex-col items-start gap-1 rounded-xl px-3 py-2.5 text-left transition-all duration-200 cursor-pointer overflow-hidden whitespace-nowrap",
                            isActive
                              ? "bg-brand/10 text-brand font-medium border border-brand/25 shadow-xs"
                              : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"
                          )}
                        >
                          <span className="w-full truncate text-xs">
                            {conversation.title || "Cuộc trò chuyện mới"}
                          </span>
                          <span className={cn(
                            "font-mono text-[10px]",
                            isActive ? "text-brand/80" : "text-muted-foreground/60"
                          )}>
                            {formatRelativeTime(conversation.updatedAt)}
                          </span>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })
                )}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
      )}

      {/* Footer menu tài khoản người dùng */}
      <SidebarFooter className={cn("py-2.5 border-t border-border overflow-hidden transition-all bg-background/50", collapsed ? "px-0 flex justify-center" : "p-2.5")}>
        <SidebarMenu className="w-full">
          <SidebarMenuItem className="w-full flex justify-center">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className={cn(
                    "w-full gap-2.5 rounded-xl transition-all hover:bg-muted/80 cursor-pointer overflow-hidden whitespace-nowrap border border-transparent hover:border-border/60",
                    collapsed ? "size-9 p-0 justify-center mx-auto" : "px-2.5 py-2"
                  )}
                >
                  <Avatar className="size-7.5 shrink-0 rounded-full border border-border">
                    <AvatarFallback className="bg-brand/15 text-xs font-semibold text-brand rounded-full">
                      {getInitials(CURRENT_USER.name)}
                    </AvatarFallback>
                  </Avatar>
                  {!collapsed && (
                    <div className="flex flex-1 items-center justify-between min-w-0 overflow-hidden">
                      <div className="flex flex-col text-left leading-tight min-w-0 overflow-hidden whitespace-nowrap">
                        <span className="truncate text-xs font-semibold text-foreground">
                          {CURRENT_USER.name}
                        </span>
                        <span className="truncate text-[10px] text-muted-foreground">
                          {CURRENT_USER.email}
                        </span>
                      </div>
                      <ChevronUp className="size-3.5 shrink-0 text-muted-foreground ml-1" />
                    </div>
                  )}
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                side="top"
                align={collapsed ? "start" : "center"}
                className="w-56 rounded-xl border border-border shadow-xl p-1"
              >
                <DropdownMenuItem onClick={() => setSettingsOpen(true)} className="rounded-lg cursor-pointer">
                  <Settings className="size-4" />
                  <span className="text-xs font-medium">Cài đặt hệ thống</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator className="bg-border" />
                <DropdownMenuItem variant="destructive" className="rounded-lg cursor-pointer">
                  <LogOut className="size-4" />
                  <span className="text-xs font-medium">Đăng xuất</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}

export function ChatSidebar({
  open,
  collapsed,
  onClose,
  onToggleCollapse,
}: {
  open: boolean;
  collapsed: boolean;
  onClose: () => void;
  onToggleCollapse: () => void;
}) {
  const init = useChatStore((s) => s.init);
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    init();
  }, [init]);

  return (
    <>
      {/* Mobile Drawer sử dụng Sheet */}
      <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
        <SheetContent side="left" showCloseButton={false} className="w-72 p-0 border-r border-border lg:hidden">
          <SheetTitle className="sr-only">Thanh bên điều hướng</SheetTitle>
          <SidebarInner
            collapsed={false}
            onClose={onClose}
            onToggleCollapse={onToggleCollapse}
            setSettingsOpen={setSettingsOpen}
          />
        </SheetContent>
      </Sheet>

      {/* Desktop Sidebar cố định */}
      <aside
        className={cn(
          "group hidden flex-col border-r border-border bg-sidebar transition-[width] duration-200 ease-linear lg:flex shrink-0 overflow-hidden",
          collapsed ? "w-16" : "w-72"
        )}
      >
        <SidebarInner
          collapsed={collapsed}
          onClose={onClose}
          onToggleCollapse={onToggleCollapse}
          setSettingsOpen={setSettingsOpen}
        />
      </aside>

      <SettingsDialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </>
  );
}

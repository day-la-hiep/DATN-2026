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
    <Sidebar className="w-full h-full border-r border-border bg-sidebar overflow-hidden" collapsible="none">
      {/* Header sidebar: khi thu gọn dùng justify-center px-0 để icon không bị lẹm viền */}
      <SidebarHeader className="p-0 py-3 overflow-hidden">
        <div className={cn("flex h-9 w-full items-center transition-all overflow-hidden", collapsed ? "justify-center px-0" : "justify-between px-3.5")}>
          <div className="flex items-center gap-2.5 min-w-0 overflow-hidden">
            {/* Logo da liễu */}
            <button
              type="button"
              onClick={collapsed ? onToggleCollapse : undefined}
              aria-label={collapsed ? "Mở rộng thanh bên" : "Trợ lý da liễu"}
              className={cn(
                "group/logo relative flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand text-brand-foreground transition-all outline-hidden",
                collapsed ? "cursor-pointer hover:bg-brand/90 hover:shadow-xs" : "cursor-default"
              )}
            >
              <Stethoscope
                className={cn(
                  "size-5 transition-all duration-200",
                  collapsed && "group-hover/logo:scale-0 group-hover/logo:opacity-0"
                )}
              />
              {collapsed && (
                <ChevronRight className="absolute size-4 text-brand-foreground opacity-0 scale-0 transition-all duration-200 group-hover/logo:scale-100 group-hover/logo:opacity-100" />
              )}
            </button>

            {!collapsed && (
              <span className="whitespace-nowrap truncate text-sm font-semibold text-foreground transition-opacity duration-200">
                Trợ lý da liễu
              </span>
            )}
          </div>

          {!collapsed && (
            <div className="flex items-center gap-1 shrink-0">
              <Button
                variant="ghost"
                size="iconSm"
                onClick={onClose}
                aria-label="Đóng menu"
                className="lg:hidden"
              >
                <X className="size-5" />
              </Button>
              <Button
                variant="ghost"
                size="iconSm"
                onClick={onToggleCollapse}
                aria-label="Thu gọn thanh bên"
                className="hidden text-muted-foreground lg:inline-flex"
              >
                <ChevronLeft className="size-4" />
              </Button>
            </div>
          )}
        </div>
      </SidebarHeader>

      {/* Tác vụ Cuộc trò chuyện mới: khi thu gọn căn giữa icon size-8 chuẩn không bị lẹm */}
      <SidebarGroup className={cn("py-1 overflow-hidden transition-all", collapsed ? "px-0 flex justify-center" : "px-3")}>
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
                "border border-border text-muted-foreground transition-colors hover:border-brand/40 hover:bg-brand/5 hover:text-brand overflow-hidden",
                collapsed
                  ? "size-8 p-0 justify-center rounded-lg mx-auto"
                  : "w-full justify-start gap-2.5 rounded-xl px-3"
              )}
            >
              <Plus className="size-4 shrink-0" />
              {!collapsed && (
                <span className="whitespace-nowrap truncate text-sm font-medium transition-opacity duration-200">
                  Cuộc trò chuyện mới
                </span>
              )}
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>

      {/* Danh sách các cuộc trò chuyện */}
      {collapsed ? (
        <div className="flex-1" />
      ) : (
        <SidebarContent className="px-3 overflow-y-auto">
          <SidebarGroup className="p-0">
            <SidebarGroupContent>
              <SidebarMenu className="gap-1">
                {loading && conversations.length === 0 ? (
                  <div className="flex flex-col gap-2">
                    {[0, 1, 2].map((i) => (
                      <SidebarMenuSkeleton key={i} className="h-10 rounded-xl" />
                    ))}
                  </div>
                ) : (
                  conversations.map((conversation) => (
                    <SidebarMenuItem key={conversation.id}>
                      <SidebarMenuButton
                        isActive={activeId === conversation.id}
                        onClick={() => {
                          selectConversation(conversation.id);
                          onClose();
                        }}
                        className={cn(
                          "h-auto w-full flex-col items-start gap-0.5 rounded-xl px-3 py-2 text-left transition-all duration-200 cursor-pointer overflow-hidden whitespace-nowrap",
                          activeId === conversation.id
                            ? "bg-muted text-foreground font-medium"
                            : "text-muted-foreground hover:bg-muted/70"
                        )}
                      >
                        <span className="w-full truncate text-sm font-medium">
                          {conversation.title || "Cuộc trò chuyện mới"}
                        </span>
                        <span className="text-xs text-muted-foreground/70">
                          {formatRelativeTime(conversation.updatedAt)}
                        </span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))
                )}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
      )}

      {/* Footer menu tài khoản người dùng: khi thu gọn căn giữa Avatar size-8 không bị lẹm */}
      <SidebarFooter className={cn("py-2 border-t border-border overflow-hidden transition-all", collapsed ? "px-0 flex justify-center" : "p-3")}>
        <SidebarMenu className="w-full">
          <SidebarMenuItem className="w-full flex justify-center">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className={cn(
                    "w-full gap-2.5 rounded-xl transition-colors hover:bg-muted/70 cursor-pointer overflow-hidden whitespace-nowrap",
                    collapsed ? "size-8 p-0 justify-center rounded-lg mx-auto" : "px-2"
                  )}
                >
                  <Avatar className="size-8 shrink-0">
                    <AvatarFallback className="bg-brand text-xs font-semibold text-brand-foreground">
                      {getInitials(CURRENT_USER.name)}
                    </AvatarFallback>
                  </Avatar>
                  {!collapsed && (
                    <div className="flex flex-1 items-center justify-between min-w-0 overflow-hidden">
                      <div className="flex flex-col text-left text-xs leading-tight min-w-0 overflow-hidden whitespace-nowrap">
                        <span className="truncate text-sm font-medium text-foreground">
                          {CURRENT_USER.name}
                        </span>
                        <span className="truncate text-xs text-muted-foreground">
                          {CURRENT_USER.email}
                        </span>
                      </div>
                      <ChevronUp className="size-4 shrink-0 text-muted-foreground ml-1" />
                    </div>
                  )}
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                side="top"
                align={collapsed ? "start" : "center"}
                className="w-56"
              >
                <DropdownMenuItem onClick={() => setSettingsOpen(true)}>
                  <Settings className="size-4" />
                  <span>Cài đặt</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive">
                  <LogOut className="size-4" />
                  <span>Đăng xuất</span>
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
      {/* Mobile Drawer sử dụng shadcn Sheet */}
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

      {/* Desktop Sidebar cố định với animation co width từ phải sang trái mượt mà */}
      <aside
        className={cn(
          "group hidden flex-col border-r border-border bg-sidebar transition-[width] duration-300 ease-in-out lg:flex shrink-0 overflow-hidden",
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

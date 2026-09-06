"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUp,
  ChevronDown,
  Cpu,
  FileText,
  Loader2,
  PanelLeft,
  Paperclip,
  Plus,
  Quote,
  Sparkles,
  SquarePen,
  X,
} from "lucide-react";
import {
  MAX_ATTACHMENTS,
  MAX_ATTACHMENT_TOTAL_BYTES,
  MODEL_OPTIONS,
  SKILL_OPTIONS,
  type SkillOption,
} from "../constants";
import { DEFAULT_INPUT_STATE, useChatStore } from "../store";
import { useComposerStore } from "../composerStore";
import { useSelectionStore } from "../selectionStore";
import type { FileAttachment, MessageSelectionRef } from "../types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn, formatBytes } from "@/lib/utils";
import { chatService } from "@/services";
import { toast } from "sonner";

export function ChatInput({
  conversationId,
  disabled,
  onOpenSidebar,
}: {
  conversationId?: string;
  disabled?: boolean;
  onOpenSidebar?: () => void;
}) {
  const activeId = useChatStore((s) => s.activeId);
  const currentConvId = conversationId ?? activeId ?? "new";

  const inputsByConversation = useChatStore((s) => s.inputsByConversation);
  const setInputStateInStore = useChatStore((s) => s.setInputState);

  const inputState = inputsByConversation[currentConvId] ?? DEFAULT_INPUT_STATE;

  const value = inputState.value;
  const selectedSkill = inputState.selectedSkill;
  const files = inputState.files;
  const pendingSelection = inputState.pendingSelection;

  const setValue = useCallback(
    (valOrFn: string | ((prev: string) => string)) => {
      const currentVal = useChatStore.getState().getInputState(currentConvId).value;
      const nextVal = typeof valOrFn === "function" ? valOrFn(currentVal) : valOrFn;
      setInputStateInStore(currentConvId, { value: nextVal });
    },
    [currentConvId, setInputStateInStore]
  );

  const setSelectedSkill = useCallback(
    (skill: SkillOption | null) => {
      setInputStateInStore(currentConvId, { selectedSkill: skill });
    },
    [currentConvId, setInputStateInStore]
  );

  const setFiles = useCallback(
    (filesOrFn: FileAttachment[] | ((prev: FileAttachment[]) => FileAttachment[])) => {
      const currentFiles = useChatStore.getState().getInputState(currentConvId).files;
      const nextFiles = typeof filesOrFn === "function" ? filesOrFn(currentFiles) : filesOrFn;
      setInputStateInStore(currentConvId, { files: nextFiles });
    },
    [currentConvId, setInputStateInStore]
  );

  const setPendingSelection = useCallback(
    (ref: MessageSelectionRef | null) => {
      setInputStateInStore(currentConvId, { pendingSelection: ref });
      useSelectionStore.getState().setPending(ref);
    },
    [currentConvId, setInputStateInStore]
  );

  const [improving, setImproving] = useState(false);
  const [skillMenuOpen, setSkillMenuOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const selectedModelId = useChatStore((s) => s.selectedModelId);
  const setModel = useChatStore((s) => s.setModel);
  const startNewChat = useChatStore((s) => s.startNewChat);
  const draft = useComposerStore((s) => s.draft);
  const setDraft = useComposerStore((s) => s.setDraft);
  const streaming = useChatStore((s) =>
    conversationId ? s.hasActiveStream(conversationId) : false
  );

  const selectedModel =
    MODEL_OPTIONS.find((m) => m.id === selectedModelId) ?? MODEL_OPTIONS[0];

  const isSlashCommand = value.startsWith("/");
  const slashMatch = isSlashCommand ? value.match(/^\/(\S*)/) : null;
  const filterQuery = slashMatch ? slashMatch[1].toLowerCase().trim() : "";

  const filteredSkills = useMemo(() => {
    if (!isSlashCommand) return [];
    if (!filterQuery) return SKILL_OPTIONS;
    return SKILL_OPTIONS.filter(
      (s) =>
        s.id.toLowerCase().includes(filterQuery) ||
        s.label.toLowerCase().includes(filterQuery) ||
        s.description.toLowerCase().includes(filterQuery)
    );
  }, [isSlashCommand, filterQuery]);

  const pendingSelections: MessageSelectionRef[] = useMemo(() => {
    if (!inputState.pendingSelection) return [];
    if (Array.isArray(inputState.pendingSelection)) return inputState.pendingSelection;
    return [inputState.pendingSelection];
  }, [inputState.pendingSelection]);

  const canSend =
    (value.trim().length > 0 || selectedSkill !== null || pendingSelections.length > 0) &&
    !disabled;

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  const handleSelectSkill = useCallback(
    (skill: SkillOption) => {
      setSelectedSkill(skill);
      setValue((prev) => prev.replace(/^\/[^\s]*\s*/, ""));
      setSkillMenuOpen(false);
      setSelectedIndex(0);
      setTimeout(() => {
        resize();
        textareaRef.current?.focus();
      }, 50);
    },
    [resize, setSelectedSkill, setValue]
  );

  const handleSend = useCallback(() => {
    if (!canSend) return;
    const fullText = selectedSkill
      ? `[Kỹ năng: ${selectedSkill.label}] ${value}`.trim()
      : value;
    sendMessage(fullText, {
      attachments: files.length ? files : undefined,
      selection: pendingSelections.length ? pendingSelections : undefined,
    });
    setSkillMenuOpen(false);
    useSelectionStore.getState().clearPendingSelections();
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [canSend, sendMessage, value, selectedSkill, files, pendingSelections]);

  const handleFiles = useCallback(
    (list: FileList | null) => {
      if (!list || list.length === 0) return;
      const incoming: FileAttachment[] = Array.from(list).map((file) => ({
        id: `${file.name}-${file.size}-${file.lastModified}`,
        name: file.name,
        size: file.size,
        type: file.type,
      }));

      setFiles((prev) => {
        const merged = [...prev];
        for (const f of incoming) {
          if (merged.some((m) => m.id === f.id)) continue; // bỏ trùng
          if (merged.length >= MAX_ATTACHMENTS) {
            toast.warning(`Tối đa ${MAX_ATTACHMENTS} tệp đính kèm.`);
            break;
          }
          if (
            merged.reduce((s, m) => s + m.size, 0) + f.size >
            MAX_ATTACHMENT_TOTAL_BYTES
          ) {
            toast.warning(
              `Tổng dung lượng đính kèm vượt ${formatBytes(MAX_ATTACHMENT_TOTAL_BYTES)}.`
            );
            break;
          }
          merged.push(f);
        }
        return merged;
      });

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    },
    [setFiles]
  );

  const handleImprove = useCallback(async () => {
    if (!value.trim() || improving || disabled) return;
    setImproving(true);
    try {
      const result = await chatService.improvePrompt(value);
      setValue(result);
      setTimeout(() => {
        resize();
        textareaRef.current?.focus();
      }, 50);
    } catch (error) {
      console.error("Lỗi khi cải thiện prompt:", error);
      toast.error("Không thể cải thiện prompt. Vui lòng thử lại sau.");
    } finally {
      setImproving(false);
    }
  }, [value, improving, disabled, resize, setValue]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setSkillMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!draft) return;
    const raf = requestAnimationFrame(() => {
      setValue(draft);
      setDraft("");
      resize();
      textareaRef.current?.focus();
    });
    return () => cancelAnimationFrame(raf);
  }, [draft, setDraft, resize, setValue]);

  useEffect(() => {
    resize();
  }, [currentConvId, value, resize]);

  return (
    <div className="bg-background p-3 sm:p-4">
      <div ref={containerRef} className="relative mx-auto max-w-3xl">
        {/* Skill menu dropdown trong Card */}
        {skillMenuOpen && isSlashCommand && (
          <Card className="absolute bottom-full left-0 right-0 z-50 mb-2 gap-0 overflow-hidden py-0 shadow-xl animate-in fade-in-0 zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-border bg-muted/40 px-3 py-2 text-xs font-semibold text-muted-foreground">
              <span className="flex items-center gap-1.5 text-foreground">
                <Sparkles className="size-3.5 text-brand" />
                Chọn Kỹ Năng (Skill)
              </span>
              <span className="text-[10px] font-normal text-muted-foreground">
                Dùng phím ↑ ↓ và Enter để chọn
              </span>
            </div>

            <div className="max-h-60 overflow-y-auto p-1">
              {filteredSkills.length > 0 ? (
                filteredSkills.map((skill, index) => {
                  const Icon = skill.icon;
                  const isSelected = index === selectedIndex;
                  return (
                    <button
                      key={skill.id}
                      type="button"
                      onClick={() => handleSelectSkill(skill)}
                      onMouseEnter={() => setSelectedIndex(index)}
                      className={cn(
                        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors cursor-pointer",
                        isSelected
                          ? "bg-brand/10 text-foreground"
                          : "hover:bg-accent text-foreground"
                      )}
                    >
                      <div
                        className={cn(
                          "flex size-7 shrink-0 items-center justify-center rounded-md border text-brand transition-colors",
                          isSelected
                            ? "border-brand/30 bg-brand/15"
                            : "border-border bg-muted"
                        )}
                      >
                        <Icon className="size-3.5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-xs font-medium">
                            {skill.label}
                          </span>
                          <span className="shrink-0 rounded bg-muted/60 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground/80">
                            /{skill.id}
                          </span>
                        </div>
                        <p className="truncate text-[11px] text-muted-foreground">
                          {skill.description}
                        </p>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="px-3 py-3 text-center text-xs text-muted-foreground">
                  Không tìm thấy kỹ năng nào phù hợp với{" "}
                  <span className="font-semibold text-foreground">
                    &quot;/{filterQuery}&quot;
                  </span>
                </div>
              )}
            </div>
          </Card>
        )}

        {/* Selected files list */}
        {files.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {files.map((file) => (
              <Badge
                key={file.id}
                variant="outline"
                className="flex items-center gap-1.5 border-border bg-muted px-2.5 py-1 text-xs text-muted-foreground"
              >
                <FileText className="size-3.5 shrink-0 text-brand" />
                <span className="max-w-45 truncate">{file.name}</span>
                <span className="shrink-0 text-muted-foreground/70">
                  {formatBytes(file.size)}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    setFiles((prev) => prev.filter((f) => f.id !== file.id))
                  }
                  aria-label={`Gỡ tệp ${file.name}`}
                  className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-destructive cursor-pointer"
                >
                  <X className="size-3.5" />
                </button>
              </Badge>
            ))}
          </div>
        )}

        {/* Pending selection banner hiển thị các đoạn trích bôi đen */}
        {pendingSelections.length > 0 && (
          <div className="mb-2 flex flex-col gap-1.5">
            {pendingSelections.map((sel, idx) => (
              <div
                key={`${sel.source}-${sel.refId}-${idx}`}
                className="flex items-center justify-between gap-2 rounded-lg border border-brand/30 bg-brand/5 px-2.5 py-1 text-xs animate-in fade-in-0 duration-150"
              >
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                  <Quote className="size-3.5 shrink-0 text-brand fill-brand/20" />
                  <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-brand/80">
                    {sel.source === "canvas"
                      ? "Canvas"
                      : sel.source === "document"
                      ? "Tài liệu"
                      : "Tin nhắn"}
                  </span>
                  <span className="truncate text-xs text-foreground font-medium">
                    “{sel.text}”
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="iconSm"
                  onClick={() => useSelectionStore.getState().removePendingSelection(idx)}
                  aria-label="Hủy chọn đoạn"
                  className="size-5 shrink-0 rounded p-0 text-muted-foreground hover:bg-brand/10 hover:text-brand cursor-pointer"
                >
                  <X className="size-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}

        {/* Input box */}
        <div className="rounded-2xl border border-input bg-muted p-2 shadow-xs focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20">
          {selectedSkill && (
            <div className="mb-1.5 flex items-center gap-1.5 px-1">
              <HoverCard>
                <HoverCardTrigger asChild>
                  <Badge
                    variant="outline"
                    className="inline-flex items-center gap-1.5 border-brand/30 bg-brand/10 px-3 py-1 text-xs font-medium text-brand transition-colors hover:bg-brand/15 cursor-pointer"
                  >
                    {(() => {
                      const Icon = selectedSkill.icon;
                      return <Icon className="size-3.5 shrink-0" />;
                    })()}
                    <span>Kỹ năng: {selectedSkill.label}</span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedSkill(null);
                      }}
                      className="ml-1 rounded-md p-0.5 text-brand/70 transition-colors hover:bg-brand/20 hover:text-brand cursor-pointer"
                      aria-label="Gỡ kỹ năng"
                    >
                      <X className="size-3.5" />
                    </button>
                  </Badge>
                </HoverCardTrigger>
                <HoverCardContent side="top" align="start" className="w-64">
                  <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                    <div className="flex size-5 items-center justify-center rounded bg-brand/15 text-brand">
                      {(() => {
                        const Icon = selectedSkill.icon;
                        return <Icon className="size-3" />;
                      })()}
                    </div>
                    {selectedSkill.label}
                  </div>
                  <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
                    {selectedSkill.description}
                  </p>
                  <div className="mt-2 flex items-center justify-between border-t border-border/50 pt-1 font-mono text-[9px] text-muted-foreground/70">
                    <span>Kỹ năng đã chọn</span>
                    <span>/{selectedSkill.id}</span>
                  </div>
                </HoverCardContent>
              </HoverCard>
            </div>
          )}

          <textarea
            ref={textareaRef}
            value={value}
            rows={1}
            disabled={disabled || improving}
            onChange={(e) => {
              const val = e.target.value;
              setValue(val);
              resize();
              if (val.startsWith("/")) {
                setSkillMenuOpen(true);
                setSelectedIndex(0);
              } else {
                setSkillMenuOpen(false);
              }
            }}
            onKeyDown={(e) => {
              if (skillMenuOpen && isSlashCommand && filteredSkills.length > 0) {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setSelectedIndex((prev) => (prev + 1) % filteredSkills.length);
                  return;
                }
                if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setSelectedIndex(
                    (prev) => (prev - 1 + filteredSkills.length) % filteredSkills.length
                  );
                  return;
                }
                if (e.key === "Enter" || e.key === "Tab") {
                  e.preventDefault();
                  if (filteredSkills[selectedIndex]) {
                    handleSelectSkill(filteredSkills[selectedIndex]);
                  }
                  return;
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  setSkillMenuOpen(false);
                  return;
                }
              }

              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!improving) {
                  handleSend();
                }
              }
            }}
            placeholder={
              disabled
                ? "Hãy bắt đầu một cuộc trò chuyện mới..."
                : improving
                ? "Đang cải thiện prompt..."
                : "Hỏi về vấn đề da liễu của bạn... (Gõ / để chọn kỹ năng)"
            }
            className="max-h-40 w-full resize-none bg-transparent px-2 py-1.5 text-sm text-foreground outline-hidden placeholder:text-muted-foreground disabled:opacity-50 font-sans"
          />
        </div>

        {/* Toolbar actions */}
        <div className="mt-1 flex items-center justify-between">
          <div className="flex items-center gap-1">
            {/* Nút mở sidebar trên mobile */}
            {onOpenSidebar && (
              <Button
                variant="ghost"
                size="iconSm"
                onClick={onOpenSidebar}
                aria-label="Mở menu thanh bên"
                className="lg:hidden text-muted-foreground"
              >
                <PanelLeft className="size-4" />
              </Button>
            )}

            {/* Plus / Extra menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="iconSm"
                  aria-label="Các chức năng thêm"
                  className="text-muted-foreground"
                >
                  <Plus className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-64">
                <DropdownMenuItem onClick={() => fileInputRef.current?.click()}>
                  <Paperclip className="size-4" />
                  <span>Đính kèm tệp</span>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => startNewChat()}>
                  <SquarePen className="size-4" />
                  <span>Cuộc trò chuyện mới</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuLabel>Mô hình</DropdownMenuLabel>
                {MODEL_OPTIONS.map((model) => (
                  <DropdownMenuItem
                    key={model.id}
                    onClick={() => setModel(model.id)}
                    className={cn(
                      model.id === selectedModelId && "bg-brand/10 font-medium"
                    )}
                  >
                    <Cpu className="size-4" />
                    <span>{model.label}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Attach file button */}
            <Button
              variant="ghost"
              size="iconSm"
              onClick={() => fileInputRef.current?.click()}
              aria-label="Đính kèm tệp"
              className="text-muted-foreground"
            >
              <Paperclip className="size-4" />
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              accept=".pdf,.doc,.docx,.txt,.md,.xls,.xlsx,.jpg,.jpeg,.png"
              onChange={(e) => handleFiles(e.target.files)}
            />

            {/* Model selector dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground gap-1.5"
                >
                  <Cpu className="size-3.5" />
                  <span>{selectedModel.label}</span>
                  <ChevronDown className="size-3" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-64">
                <DropdownMenuRadioGroup
                  value={selectedModelId}
                  onValueChange={(val) => setModel(val)}
                >
                  {MODEL_OPTIONS.map((model) => (
                    <DropdownMenuRadioItem
                      key={model.id}
                      value={model.id}
                      className="flex flex-col items-start gap-0.5 py-2"
                    >
                      <span className="text-xs font-medium text-foreground">
                        {model.label}
                      </span>
                      <span className="text-[11px] leading-snug text-muted-foreground">
                        {model.description}
                      </span>
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <div className="flex items-center gap-2">
            {value.trim().length > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleImprove}
                disabled={improving || disabled}
                className="text-brand hover:text-brand/80 hover:bg-brand/5 gap-1.5 h-8 px-2.5 rounded-lg border border-brand/20 bg-brand/5 transition-all text-xs font-medium"
              >
                {improving ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Sparkles className="size-3.5" />
                )}
                <span>Cải thiện</span>
              </Button>
            )}

            <Button
              variant="default"
              size="iconSm"
              onClick={handleSend}
              disabled={!canSend || improving}
              aria-label="Gửi tin nhắn"
              className="shrink-0 rounded-full transition-all"
            >
              <ArrowUp className="size-4 text-current" />
            </Button>
          </div>
        </div>

        <div className="mt-2 flex items-center justify-center gap-2 text-center text-xs text-muted-foreground">
          {streaming && (
            <span className="flex items-center gap-1 font-medium text-brand">
              <Loader2 className="size-3 animate-spin" />
              AI đang trả lời — bạn vẫn có thể gửi tiếp câu hỏi
            </span>
          )}
          {!streaming && (
            <span>
              Thông tin chỉ mang tính tham khảo, không thay thế thăm khám và tư
              vấn của bác sĩ da liễu.
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

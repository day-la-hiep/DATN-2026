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
  Sparkles,
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
import { ImageThumbnail } from "./ImageThumbnail";
import { useComposerStore } from "../composerStore";
import { useSelectionStore } from "../selectionStore";
import type { FileAttachment, MessageSelectionRef } from "../types";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
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

  const [improving, setImproving] = useState(false);
  const [skillMenuOpen, setSkillMenuOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const selectedModelId = useChatStore((s) => s.selectedModelId);
  const setModel = useChatStore((s) => s.setModel);
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

  const hasPendingUploads = files.some((f) => f.uploaded === false);

  const canSend =
    (value.trim().length > 0 || selectedSkill !== null || pendingSelections.length > 0) &&
    !disabled &&
    !hasPendingUploads;

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
      const incomingFiles = Array.from(list);
      const isImage = (f: File) => f.type.startsWith("image/");
      const incoming: FileAttachment[] = incomingFiles.map((file) => ({
        id: `${file.name}-${file.size}-${file.lastModified}`,
        name: file.name,
        size: file.size,
        type: file.type,
        url: isImage(file) ? URL.createObjectURL(file) : undefined,
        uploaded: isImage(file) ? false : undefined,
      }));

      const accepted: { attachment: FileAttachment; file: File }[] = [];

      setFiles((prev) => {
        const merged = [...prev];
        for (let i = 0; i < incoming.length; i++) {
          const f = incoming[i];
          if (merged.some((m) => m.id === f.id)) continue;
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
          accepted.push({ attachment: f, file: incomingFiles[i] });
        }
        return merged;
      });

      for (const { attachment, file } of accepted) {
        if (!isImage(file)) continue;
        const tempId = attachment.id;
        chatService
          .uploadAttachment(file)
          .then((uploaded) => {
            setFiles((prev) =>
              prev.map((f) =>
                f.id === tempId
                  ? { ...uploaded, url: uploaded.url || f.url }
                  : f
              )
            );
          })
          .catch((error) => {
            console.error("Upload ảnh thất bại", error);
            toast.error(`Không upload được ảnh "${file.name}".`);
            setFiles((prev) => prev.filter((f) => f.id !== tempId));
          });
      }

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
    <div className="bg-background/80 backdrop-blur-md p-3 sm:p-4 border-t border-border/80">
      <div ref={containerRef} className="relative mx-auto max-w-4xl">
        {/* Skill menu dropdown trong Card */}
        {skillMenuOpen && isSlashCommand && (
          <div className="absolute bottom-full left-0 right-0 z-50 mb-3 overflow-hidden rounded-2xl border border-border bg-card/95 backdrop-blur-md shadow-xl animate-in fade-in-0 duration-150">
            <div className="flex items-center justify-between border-b border-border/60 bg-muted/50 px-3.5 py-2.5 font-mono text-xs text-foreground">
              <span className="flex items-center gap-2 text-brand font-medium">
                <Sparkles className="size-3.5" />
                Chọn kỹ năng y khoa (Skill)
              </span>
              <span className="text-muted-foreground text-[10px]">
                [↑ / ↓] Điều hướng • [Enter] Chọn
              </span>
            </div>

            <div className="max-h-60 overflow-y-auto p-1.5">
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
                        "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all cursor-pointer",
                        isSelected
                          ? "bg-brand/10 text-brand"
                          : "hover:bg-muted/70 text-foreground"
                      )}
                    >
                      <div
                        className={cn(
                          "flex size-8 shrink-0 items-center justify-center rounded-lg border font-mono text-xs",
                          isSelected ? "border-brand/40 bg-brand text-white shadow-xs" : "border-border bg-muted text-brand"
                        )}
                      >
                        <Icon className="size-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-xs font-semibold">
                            {skill.label}
                          </span>
                          <span className={cn(
                            "shrink-0 font-mono text-[10px] px-1.5 py-0.5 rounded border",
                            isSelected ? "border-brand/40 bg-brand/15 text-brand" : "border-border bg-muted/60 text-muted-foreground"
                          )}>
                            /{skill.id}
                          </span>
                        </div>
                        <p className={cn(
                          "truncate text-xs mt-0.5",
                          isSelected ? "text-brand/80" : "text-muted-foreground"
                        )}>
                          {skill.description}
                        </p>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="px-3 py-3 text-center font-mono text-xs text-muted-foreground">
                  Không tìm thấy kỹ năng: &quot;/{filterQuery}&quot;
                </div>
              )}
            </div>
          </div>
        )}

        {/* Selected files list */}
        {files.length > 0 && (
          <div className="mb-2.5 flex flex-wrap items-center gap-2">
            {files.map((file) => {
              const isImage = file.type.startsWith("image/") && file.url;
              if (isImage) {
                return (
                  <div key={file.id} className="rounded-xl overflow-hidden border border-border shadow-xs">
                    <ImageThumbnail
                      url={file.url!}
                      name={file.name}
                      size={72}
                      fileSize={file.size}
                      uploading={file.uploaded === false}
                      onRemove={() =>
                        setFiles((prev) => prev.filter((f) => f.id !== file.id))
                      }
                    />
                  </div>
                );
              }
              return (
                <div
                  key={file.id}
                  className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-1.5 text-xs text-foreground shadow-xs"
                >
                  <FileText className="size-3.5 text-brand" />
                  <span className="max-w-45 truncate font-medium">
                    {file.name}
                  </span>
                  <span className="text-[10px] font-mono text-muted-foreground">
                    [{formatBytes(file.size)}]
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setFiles((prev) => prev.filter((f) => f.id !== file.id))
                    }
                    aria-label={`Gỡ tệp ${file.name}`}
                    className="p-1 rounded-md text-muted-foreground hover:bg-muted hover:text-brand cursor-pointer"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Pending selection banner */}
        {pendingSelections.length > 0 && (
          <div className="mb-2 flex flex-col gap-1.5">
            {pendingSelections.map((sel, idx) => (
              <div
                key={`${sel.source}-${sel.refId}-${idx}`}
                className="flex items-center justify-between gap-2 rounded-xl border border-brand/30 bg-brand/5 p-2.5 text-xs shadow-xs"
              >
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <span className="text-brand font-mono text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-brand/10 shrink-0">
                    {sel.source === "canvas" ? "CANVAS" : sel.source === "document" ? "TÀI LIỆU" : "TIN NHẮN"}
                  </span>
                  <span className="truncate text-foreground font-medium">
                    “{sel.text}”
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => useSelectionStore.getState().removePendingSelection(idx)}
                  aria-label="Hủy chọn đoạn"
                  className="p-1 rounded-md text-muted-foreground hover:bg-brand/10 hover:text-brand cursor-pointer shrink-0"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Input box */}
        <div className="rounded-2xl border border-border bg-card/90 shadow-sm p-3 focus-within:border-brand/50 focus-within:ring-2 focus-within:ring-brand/20 transition-all">
          {selectedSkill && (
            <div className="mb-2 flex items-center gap-1.5">
              <div className="inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand/10 px-3 py-1 text-brand font-mono text-xs font-medium">
                {(() => {
                  const Icon = selectedSkill.icon;
                  return <Icon className="size-3 shrink-0" />;
                })()}
                <span>Kỹ năng: {selectedSkill.label}</span>
                <button
                  type="button"
                  onClick={() => setSelectedSkill(null)}
                  className="ml-1 text-brand/70 hover:text-brand cursor-pointer"
                  aria-label="Gỡ kỹ năng"
                >
                  <X className="size-3" />
                </button>
              </div>
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
            onPaste={(e) => {
              if (e.clipboardData.files && e.clipboardData.files.length > 0) {
                const incomingList = Array.from(e.clipboardData.files);
                const hasImages = incomingList.some((f) => f.type.startsWith("image/"));
                if (hasImages) {
                  e.preventDefault();
                  handleFiles(e.clipboardData.files);
                }
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
                ? "Bắt đầu một cuộc trò chuyện mới..."
                : improving
                ? "Đang tối ưu câu hỏi với AI..."
                : "Hỏi về vấn đề da liễu của bạn... (Gõ / để chọn kỹ năng)"
            }
            className="max-h-40 w-full resize-none bg-transparent px-2 py-1 text-sm sm:text-base text-foreground outline-hidden placeholder:text-muted-foreground/60 disabled:opacity-40 font-normal leading-relaxed"
          />

          {/* Toolbar actions */}
          <div className="mt-2.5 flex items-center justify-between border-t border-border/60 pt-2.5">
            <div className="flex items-center gap-2 flex-wrap">
              {/* Mobile Sidebar toggle */}
              {onOpenSidebar && (
                <Button
                  variant="ghost"
                  size="iconSm"
                  onClick={onOpenSidebar}
                  aria-label="Mở menu thanh bên"
                  className="lg:hidden rounded-lg text-muted-foreground hover:text-foreground"
                >
                  <PanelLeft className="size-4" />
                </Button>
              )}

              {/* Attach file button */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                aria-label="Đính kèm tệp"
                className="flex items-center gap-1.5 rounded-lg border border-border/80 bg-background px-2.5 py-1.5 text-xs font-medium text-foreground hover:border-brand/40 hover:bg-muted transition-all cursor-pointer"
              >
                <Paperclip className="size-3.5 text-brand" />
                <span className="hidden sm:inline">Đính kèm</span>
              </button>
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
                  <button
                    type="button"
                    className="flex items-center gap-1.5 rounded-lg border border-border/80 bg-background px-2.5 py-1.5 text-xs font-medium text-foreground hover:border-brand/40 hover:bg-muted transition-all cursor-pointer"
                  >
                    <Cpu className="size-3.5 text-brand" />
                    <span>{selectedModel.label}</span>
                    <ChevronDown className="size-3.5 opacity-60" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-64 rounded-xl border border-border shadow-xl p-1">
                  <DropdownMenuRadioGroup
                    value={selectedModelId}
                    onValueChange={(val) => setModel(val)}
                  >
                    {MODEL_OPTIONS.map((model) => (
                      <DropdownMenuRadioItem
                        key={model.id}
                        value={model.id}
                        className="flex flex-col items-start gap-0.5 py-2 rounded-lg"
                      >
                        <span className="text-xs font-semibold text-foreground">
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
                <button
                  type="button"
                  onClick={handleImprove}
                  disabled={improving || disabled}
                  className="flex items-center gap-1.5 rounded-lg border border-brand/30 bg-brand/5 px-3 py-1.5 text-xs font-medium text-brand hover:bg-brand hover:text-white transition-all cursor-pointer disabled:opacity-40"
                >
                  {improving ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="size-3.5" />
                  )}
                  <span>Tối ưu câu hỏi</span>
                </button>
              )}

              <button
                type="button"
                onClick={handleSend}
                disabled={!canSend || improving}
                aria-label="Gửi tin nhắn"
                className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-r from-[var(--brand)] to-[var(--brand-secondary,#4d7cff)] text-white shadow-xs hover:shadow-accent hover:-translate-y-0.5 active:scale-[0.98] transition-all disabled:pointer-events-none disabled:opacity-30 cursor-pointer"
              >
                <ArrowUp className="size-4.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Disclaimer */}
        <div className="mt-2 text-center text-xs text-muted-foreground">
          {streaming ? (
            <span className="flex items-center justify-center gap-2 font-medium text-brand">
              <span className="size-2 rounded-full bg-brand animate-pulse-subtle" />
              Hệ thống đang tư vấn — bạn có thể tiếp tục nhập câu hỏi
            </span>
          ) : (
            <span>
              Lưu ý: Thông tin tư vấn chỉ mang tính tham khảo, không thay thế chẩn đoán chuyên khoa của bác sĩ.
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

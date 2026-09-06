"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { toast } from "sonner";
import {
  Bell,
  Blocks,
  Bot,
  Check,
  KeyRound,
  Languages,
  Palette,
  PenLine,
  Plus,
  Save,
  Search,
  Settings2,
  Sparkles,
  Stethoscope,
  Trash2,
  UserRound,
  WandSparkles,
  type LucideIcon,
} from "lucide-react";
import { CURRENT_USER } from "@/features/user";
import { useChatStore } from "@/features/chat/store";
import { useComposerStore } from "@/features/chat/composerStore";
import { BRAND_OPTIONS, useBrandStore } from "../store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type SectionId =
  | "general"
  | "appearance"
  | "notifications"
  | "account"
  | "skills"
  | "agents"
  | "plugins";

interface SectionItem {
  id: SectionId;
  label: string;
  icon: LucideIcon;
}

/** Sidebar chia theo nhóm: phần Chung và phần Mở rộng (skill/agent/plugin) */
const SECTION_GROUPS: { label: string; items: SectionItem[] }[] = [
  {
    label: "Chung",
    items: [
      { id: "general", label: "Cài đặt chung", icon: Settings2 },
      { id: "appearance", label: "Giao diện", icon: Palette },
      { id: "notifications", label: "Thông báo", icon: Bell },
      { id: "account", label: "Tài khoản", icon: UserRound },
    ],
  },
  {
    label: "Mở rộng",
    items: [
      { id: "skills", label: "Kỹ năng", icon: WandSparkles },
      { id: "agents", label: "Agent", icon: Bot },
      { id: "plugins", label: "Plugin", icon: Blocks },
    ],
  },
];

const LANGUAGES = ["Tiếng Việt", "English"];

interface ExtensionItem {
  id: string;
  label: string;
  description?: string;
  icon: LucideIcon;
}

const SKILLS: ExtensionItem[] = [
  {
    id: "draft",
    label: "Soạn hướng dẫn chăm sóc da",
    description: "Phác đồ điều trị, hướng dẫn dùng thuốc, chăm sóc tại nhà...",
    icon: WandSparkles,
  },
  {
    id: "search",
    label: "Tra cứu tài liệu y khoa",
    description: "Tìm hướng dẫn chẩn đoán, phác đồ điều trị liên quan",
    icon: Search,
  },
  {
    id: "analyze",
    label: "Phân tích triệu chứng da",
    description: "Đánh giá tổn thương da và mức độ nghiêm trọng",
    icon: Stethoscope,
  },
  {
    id: "translate",
    label: "Dịch thuật y khoa",
    description: "Dịch tài liệu, đơn thuốc song ngữ",
    icon: Languages,
  },
];

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function ToggleRow({
  label,
  description,
  icon: Icon,
  checked,
  onChange,
}: {
  label: string;
  description?: string;
  icon?: LucideIcon;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="flex w-full items-center justify-between gap-4 rounded-xl border border-border px-3 py-2.5">
      <span className="flex items-start gap-2.5">
        {Icon && (
          <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <span>
          <span className="block text-sm font-medium text-foreground">
            {label}
          </span>
          {description && (
            <span className="block text-xs text-muted-foreground">
              {description}
            </span>
          )}
        </span>
      </span>
      <Switch
        checked={checked}
        onCheckedChange={onChange}
        aria-label={label}
      />
    </div>
  );
}

function ToggleList({
  items,
  values,
  onChange,
}: {
  items: ExtensionItem[];
  values: Record<string, boolean>;
  onChange: (id: string, value: boolean) => void;
}) {
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <ToggleRow
          key={item.id}
          label={item.label}
          description={item.description}
          icon={item.icon}
          checked={!!values[item.id]}
          onChange={(v) => onChange(item.id, v)}
        />
      ))}
    </div>
  );
}

function SectionHeading({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div>
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      <p className="text-xs text-muted-foreground">{description}</p>
    </div>
  );
}

function SettingsContent({ onClose }: { onClose: () => void }) {
  const { theme, setTheme } = useTheme();
  const brand = useBrandStore((s) => s.brand);
  const setBrand = useBrandStore((s) => s.setBrand);
  const router = useRouter();
  const startNewChat = useChatStore((s) => s.startNewChat);
  const setDraft = useComposerStore((s) => s.setDraft);

  const [section, setSection] = useState<SectionId>("general");
  const [name, setName] = useState(CURRENT_USER.name);
  const [email] = useState(CURRENT_USER.email);
  const [language, setLanguage] = useState("Tiếng Việt");
  const [notifyEmail, setNotifyEmail] = useState(true);
  const [notifyPush, setNotifyPush] = useState(false);

  const [skillValues, setSkillValues] = useState<Record<string, boolean>>({
    draft: true,
    search: true,
    analyze: true,
    translate: false,
  });
  const [skillMenuOpen, setSkillMenuOpen] = useState(false);

  /** "Sử dụng model": về trang chat chính, mở hội thoại mới và chèn prompt sẵn */
  const createSkillWithModel = () => {
    setSkillMenuOpen(false);
    onClose();
    startNewChat();
    setDraft(
      "Tôi muốn tạo một skill mới. Bạn hãy hỏi tôi tên, mô tả và chức năng mong muốn, rồi đề xuất cấu hình skill hoàn chỉnh để tôi xác nhận."
    );
    router.push("/chats");
  };

  const toggleIn =
    (setter: React.Dispatch<React.SetStateAction<Record<string, boolean>>>) =>
    (id: string, value: boolean) =>
      setter((prev) => ({ ...prev, [id]: value }));

  const handleSave = () => {
    localStorage.setItem("derma-ai-user-name", name);
    toast.success("Đã lưu thay đổi");
  };

  return (
    <>
      {/* cột trái: danh sách mục chia theo nhóm */}
      <aside className="w-full shrink-0 border-b border-border bg-muted/40 md:w-52 md:border-r md:border-b-0">
        <nav className="flex gap-1 overflow-x-auto p-2 md:flex-col">
          {SECTION_GROUPS.map((group) => (
            <div
              key={group.label}
              className="md:flex md:flex-col"
            >
              {group.items.map(({ id, label, icon: Icon }, index) => (
                <div key={id}>
                  {group.label !== "Chung" && index === 0 && (
                    <>
                      <p className="hidden px-3 pb-1 pt-2 text-[10px] font-semibold tracking-wide text-muted-foreground/70 uppercase md:block">
                        {group.label}
                      </p>
                      <div className="mx-3 my-1 hidden h-px bg-border md:block" />
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => setSection(id)}
                    className={cn(
                      "flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors md:w-full cursor-pointer",
                      section === id
                        ? "bg-brand text-brand-foreground"
                        : "text-muted-foreground hover:bg-muted"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {label}
                  </button>
                </div>
              ))}
            </div>
          ))}
        </nav>
      </aside>

      {/* cột phải: nội dung mục đang chọn */}
      <div className="min-w-0 flex-1 overflow-y-auto bg-card p-5">
        {section === "general" && (
          <div className="space-y-5">
            <SectionHeading
              title="Cài đặt chung"
              description="Thông tin cơ bản của tài khoản bạn."
            />
            <Field label="Tên hiển thị">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <Field label="Email">
              <Input
                value={email}
                readOnly
                className="text-muted-foreground"
              />
            </Field>
            <Field label="Ngôn ngữ">
              <Select
                value={language}
                onValueChange={(val) => setLanguage(val)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Chọn ngôn ngữ" />
                </SelectTrigger>
                <SelectContent>
                  {LANGUAGES.map((lang) => (
                    <SelectItem key={lang} value={lang}>
                      {lang}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Button onClick={handleSave}>
              <Save className="h-4 w-4" />
              Lưu thay đổi
            </Button>
          </div>
        )}

        {section === "appearance" && (
          <div className="space-y-5">
            <SectionHeading
              title="Giao diện"
              description="Tùy chỉnh cách hiển thị của ứng dụng."
            />
            <Field label="Chủ đề">
              <Select
                value={theme ?? "system"}
                onValueChange={(val) => setTheme(val)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Chọn chủ đề" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="system">Theo hệ thống</SelectItem>
                  <SelectItem value="light">Sáng</SelectItem>
                  <SelectItem value="dark">Tối</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-muted-foreground">
                Màu chủ đạo
              </span>
              <div className="flex flex-wrap gap-2">
                {BRAND_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setBrand(option.id)}
                    className={cn(
                      "flex items-center gap-2 rounded-xl border px-3 py-2 text-sm transition-colors cursor-pointer",
                      brand === option.id
                        ? "border-brand bg-brand/10 text-foreground"
                        : "border-border text-muted-foreground hover:bg-muted"
                    )}
                  >
                    <span
                      className="h-4 w-4 rounded-full"
                      style={{ backgroundColor: option.color }}
                    />
                    {option.label}
                    {brand === option.id && (
                      <Check className="h-3.5 w-3.5 text-brand" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {section === "notifications" && (
          <div className="space-y-5">
            <SectionHeading
              title="Thông báo"
              description="Chọn cách bạn muốn nhận thông báo."
            />
            <ToggleRow
              label="Thông báo qua email"
              description="Nhận cập nhật qua địa chỉ email của bạn"
              checked={notifyEmail}
              onChange={setNotifyEmail}
            />
            <ToggleRow
              label="Thông báo đẩy"
              description="Nhận thông báo đẩy trên trình duyệt"
              checked={notifyPush}
              onChange={setNotifyPush}
            />
          </div>
        )}

        {section === "account" && (
          <div className="space-y-5">
            <SectionHeading
              title="Tài khoản"
              description="Quản lý thông tin bảo mật của tài khoản."
            />
            <div className="flex items-center justify-between gap-4 rounded-xl border border-border px-3 py-2.5">
              <span className="flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium text-foreground">
                  Mật khẩu
                </span>
              </span>
              <Button variant="outline" size="sm">
                Đổi mật khẩu
              </Button>
            </div>
            <div className="flex items-center justify-between gap-4 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5">
              <span className="text-sm font-medium text-destructive">
                Xóa tài khoản
              </span>
              <Button variant="destructive" size="sm">
                <Trash2 className="h-3.5 w-3.5" />
                Xóa
              </Button>
            </div>
          </div>
        )}

        {section === "skills" && (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <SectionHeading
                title="Kỹ năng"
                description="Danh sách kỹ năng đã tạo và quản lý."
              />
              <div className="relative shrink-0">
                <Button size="sm" onClick={() => setSkillMenuOpen((v) => !v)}>
                  <Plus className="h-4 w-4" />
                  Thêm skill
                </Button>
                {skillMenuOpen && (
                  <>
                    <div
                      className="fixed inset-0 z-40"
                      onClick={() => setSkillMenuOpen(false)}
                    />
                    <div className="absolute right-0 top-full z-50 mt-1 w-64 rounded-xl border border-border bg-popover p-1 text-popover-foreground shadow-lg animate-in fade-in-0 zoom-in-95 duration-150">
                      <button
                        type="button"
                        onClick={() => {
                          setSkillMenuOpen(false);
                          toast.info("Tự tạo skill — sắp triển khai");
                        }}
                        className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-foreground transition-colors hover:bg-accent cursor-pointer"
                      >
                        <PenLine className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="min-w-0 flex-1">
                          <span className="block">Tự tạo</span>
                          <span className="block text-[11px] text-muted-foreground">
                            Nhập tên, mô tả và cấu hình skill
                          </span>
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={createSkillWithModel}
                        className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-foreground transition-colors hover:bg-accent cursor-pointer"
                      >
                        <Sparkles className="h-4 w-4 shrink-0 text-brand" />
                        <span className="min-w-0 flex-1">
                          <span className="block">Sử dụng model</span>
                          <span className="block text-[11px] text-muted-foreground">
                            Mô tả nhu cầu, model tạo skill tự động
                          </span>
                        </span>
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
            <ToggleList
              items={SKILLS}
              values={skillValues}
              onChange={toggleIn(setSkillValues)}
            />
          </div>
        )}

        {section === "agents" && (
          <div className="flex min-h-48 flex-col items-center justify-center gap-2 text-center">
            <Bot className="h-8 w-8 text-muted-foreground/50" />
            <p className="text-sm font-medium text-foreground">Agent</p>
            <p className="text-xs text-muted-foreground">
              Tính năng đang được phát triển.
            </p>
          </div>
        )}

        {section === "plugins" && (
          <div className="flex min-h-48 flex-col items-center justify-center gap-2 text-center">
            <Blocks className="h-8 w-8 text-muted-foreground/50" />
            <p className="text-sm font-medium text-foreground">Plugin</p>
            <p className="text-xs text-muted-foreground">
              Tính năng đang được phát triển.
            </p>
          </div>
        )}
      </div>
    </>
  );
}

/** Cửa sổ cài đặt nhỏ nổi trên giao diện chat sử dụng shadcn Dialog chuẩn */
export function SettingsDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(val) => !val && onClose()}>
      <DialogContent className="max-w-5xl sm:max-w-5xl h-[700px] max-h-[90vh] p-0 gap-0 overflow-hidden rounded-2xl flex flex-col">
        <DialogHeader className="border-b border-border px-4 py-3 text-left">
          <DialogTitle className="text-sm font-semibold text-foreground">Cài đặt</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Tùy chỉnh ứng dụng và tài khoản của bạn
          </DialogDescription>
        </DialogHeader>
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <SettingsContent onClose={onClose} />
        </div>
        <div className="flex items-center justify-between border-t border-border px-4 py-3 bg-card">
          <p className="text-xs text-muted-foreground">
            Thay đổi được lưu trên trình duyệt của bạn
          </p>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Đóng
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

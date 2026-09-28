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

const SECTION_GROUPS: { code: string; label: string; items: SectionItem[] }[] = [
  {
    code: "01",
    label: "CÀI ĐẶT CHUNG",
    items: [
      { id: "general", label: "Thông tin cơ bản", icon: Settings2 },
      { id: "appearance", label: "Giao diện & Màu sắc", icon: Palette },
      { id: "notifications", label: "Thông báo", icon: Bell },
      { id: "account", label: "Tài khoản & Bảo mật", icon: UserRound },
    ],
  },
  {
    code: "02",
    label: "MỞ RỘNG Y KHOA",
    items: [
      { id: "skills", label: "Kỹ năng chuyên môn", icon: WandSparkles },
      { id: "agents", label: "AI Agent", icon: Bot },
      { id: "plugins", label: "Tiện ích bổ sung", icon: Blocks },
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
      <span className="text-xs font-semibold text-foreground">
        {label}
      </span>
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
    <div className="flex w-full items-center justify-between gap-4 rounded-xl border border-border bg-card/80 p-3.5 shadow-xs transition-colors">
      <span className="flex items-start gap-3">
        {Icon && (
          <Icon className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
        )}
        <span>
          <span className="block text-xs font-medium text-foreground">
            {label}
          </span>
          {description && (
            <span className="block text-xs text-muted-foreground mt-0.5">
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
    <div className="space-y-2.5">
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
    <div className="border-b border-border/60 pb-3 mb-4">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
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
    toast.success("ĐÃ LƯU THAY ĐỔI CẤU HÌNH");
  };

  return (
    <>
      {/* Cột trái: menu phân mục */}
      <aside className="w-full shrink-0 border-b border-border bg-muted/30 md:w-64 md:border-r md:border-b-0">
        <nav className="flex gap-1 overflow-x-auto p-3 md:flex-col">
          {SECTION_GROUPS.map((group) => (
            <div key={group.code} className="md:flex md:flex-col mb-2">
              <div className="hidden px-3 pt-2 pb-1 font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground md:block">
                {group.label}
              </div>
              {group.items.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setSection(id)}
                  className={cn(
                    "flex shrink-0 items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-medium transition-all md:w-full cursor-pointer",
                    section === id
                      ? "bg-brand/10 text-brand font-semibold shadow-xs"
                      : "text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0 text-current" />
                  <span className="truncate">{label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
      </aside>

      {/* Cột phải: nội dung */}
      <div className="min-w-0 flex-1 overflow-y-auto bg-background p-6">
        {section === "general" && (
          <div className="space-y-6">
            <SectionHeading
              title="Cài đặt chung"
              description="Thông tin định danh người dùng và ngôn ngữ hiển thị"
            />
            <Field label="Tên hiển thị">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="font-medium"
              />
            </Field>
            <Field label="Địa chỉ Email">
              <Input
                value={email}
                readOnly
                className="text-muted-foreground font-mono"
              />
            </Field>
            <Field label="Ngôn ngữ hệ thống">
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
            <Button onClick={handleSave} className="rounded-xl">
              <Save className="h-4 w-4 mr-1.5" />
              <span>Lưu thay đổi</span>
            </Button>
          </div>
        )}

        {section === "appearance" && (
          <div className="space-y-6">
            <SectionHeading
              title="Giao diện & Màu sắc"
              description="Tùy biến theme và bảng màu theo Minimalist Modern"
            />
            <Field label="Chế độ hiển thị">
              <Select
                value={theme ?? "system"}
                onValueChange={(val) => setTheme(val)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Chọn chủ đề" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="system">Theo hệ thống</SelectItem>
                  <SelectItem value="light">Chế độ sáng (Warm Minimalist)</SelectItem>
                  <SelectItem value="dark">Chế độ tối (Midnight Slate)</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <div className="flex flex-col gap-2">
              <span className="text-xs font-semibold text-foreground">
                Tông màu nhấn (Accent)
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                {BRAND_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setBrand(option.id)}
                    className={cn(
                      "flex items-center justify-between border px-3 py-2.5 text-xs font-medium transition-all cursor-pointer rounded-xl",
                      brand === option.id
                        ? "border-brand bg-brand/10 text-brand shadow-xs"
                        : "border-border text-foreground hover:bg-muted/70"
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className="h-3.5 w-3.5 rounded-full border border-black/10"
                        style={{ backgroundColor: option.color }}
                      />
                      <span>{option.label}</span>
                    </span>
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
          <div className="space-y-4">
            <SectionHeading
              title="Thông báo"
              description="Phương thức tiếp nhận cập nhật từ hệ thống y tế"
            />
            <ToggleRow
              label="Thông báo qua email"
              description="Nhận cập nhật hồ sơ và kết quả tư vấn qua email"
              checked={notifyEmail}
              onChange={setNotifyEmail}
            />
            <ToggleRow
              label="Thông báo đẩy"
              description="Nhận thông báo đẩy thời gian thực trên trình duyệt"
              checked={notifyPush}
              onChange={setNotifyPush}
            />
          </div>
        )}

        {section === "account" && (
          <div className="space-y-4">
            <SectionHeading
              title="Tài khoản & Bảo mật"
              description="Quản lý mật khẩu và quyền riêng tư dữ liệu"
            />
            <div className="flex items-center justify-between gap-4 rounded-xl border border-border p-4 shadow-xs">
              <span className="flex items-center gap-2.5">
                <KeyRound className="h-4 w-4 text-brand" />
                <span className="text-xs font-medium text-foreground">
                  Mật khẩu đăng nhập
                </span>
              </span>
              <Button variant="outline" size="sm" className="rounded-xl">
                Đổi mật khẩu
              </Button>
            </div>
            <div className="flex items-center justify-between gap-4 rounded-xl border border-destructive/30 bg-destructive/5 p-4 shadow-xs">
              <span className="text-xs font-medium text-destructive">
                Xóa tài khoản và dữ liệu
              </span>
              <Button variant="destructive" size="sm" className="rounded-xl">
                <Trash2 className="h-3.5 w-3.5 mr-1" />
                Xóa vĩnh viễn
              </Button>
            </div>
          </div>
        )}

        {section === "skills" && (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <SectionHeading
                title="Kỹ năng y khoa"
                description="Quản lý các module chuyên môn hoạt động trong chat"
              />
              <div className="relative shrink-0">
                <Button size="sm" onClick={() => setSkillMenuOpen((v) => !v)} className="rounded-xl">
                  <Plus className="h-4 w-4 mr-1" />
                  Thêm kỹ năng
                </Button>
                {skillMenuOpen && (
                  <>
                    <div
                      className="fixed inset-0 z-40"
                      onClick={() => setSkillMenuOpen(false)}
                    />
                    <div className="absolute right-0 top-full z-50 mt-1 w-64 rounded-xl border border-border bg-card p-1 shadow-xl animate-in fade-in-0 duration-150">
                      <button
                        type="button"
                        onClick={() => {
                          setSkillMenuOpen(false);
                          toast.info("Tự tạo skill — sắp triển khai");
                        }}
                        className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs font-medium text-foreground transition-colors hover:bg-muted cursor-pointer"
                      >
                        <PenLine className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="min-w-0 flex-1">
                          <span className="block">Tự tạo cấu hình</span>
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={createSkillWithModel}
                        className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs font-medium text-foreground transition-colors hover:bg-muted cursor-pointer"
                      >
                        <Sparkles className="h-4 w-4 shrink-0 text-brand" />
                        <span className="min-w-0 flex-1">
                          <span className="block">Tạo với AI Agent</span>
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
          <div className="flex min-h-48 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border p-6 text-center">
            <Bot className="h-8 w-8 text-brand" />
            <p className="font-semibold text-xs text-foreground">AI AGENTS WORKFORCE</p>
            <p className="text-xs text-muted-foreground">
              Module đang được phát triển và tích hợp thêm
            </p>
          </div>
        )}

        {section === "plugins" && (
          <div className="flex min-h-48 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border p-6 text-center">
            <Blocks className="h-8 w-8 text-brand" />
            <p className="font-semibold text-xs text-foreground">PLUGINS & INTEGRATIONS</p>
            <p className="text-xs text-muted-foreground">
              Module đang được phát triển và tích hợp thêm
            </p>
          </div>
        )}
      </div>
    </>
  );
}

export function SettingsDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(val) => !val && onClose()}>
      <DialogContent className="max-w-4xl sm:max-w-4xl h-[650px] max-h-[90vh] p-0 gap-0 overflow-hidden rounded-2xl border border-border flex flex-col shadow-2xl">
        <DialogHeader className="border-b border-border/80 px-6 py-4 text-left bg-background/60 backdrop-blur-xs">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-brand" />
            <span className="font-mono text-xs uppercase tracking-wider text-brand font-medium">
              Cấu hình hệ thống
            </span>
          </div>
          <DialogTitle className="text-lg font-serif font-normal tracking-tight text-foreground mt-0.5">
            Cài đặt ứng dụng
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Tùy chỉnh hồ sơ và thông số vận hành của trợ lý y khoa
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <SettingsContent onClose={onClose} />
        </div>

        <div className="flex items-center justify-between border-t border-border px-6 py-3.5 bg-card/60">
          <p className="text-xs text-muted-foreground">
            Dữ liệu được lưu trữ cục bộ an toàn trên trình duyệt
          </p>
          <Button variant="outline" size="sm" onClick={onClose} className="rounded-xl">
            Đóng
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

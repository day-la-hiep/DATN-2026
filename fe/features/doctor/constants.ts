import {
  Clock,
  CheckCircle2,
  CircleDot,
  Activity,
  Microscope,
  History,
  Pill,
  AlertTriangle,
  ImageIcon,
  HelpCircle,
  HandHelping,
  type LucideIcon,
} from "lucide-react";
import type { ClinicalFactType, ConsultationStatus } from "./types";

/** Cấu hình hiển thị theo loại Dữ kiện lâm sàng (bám sát bảng clinical_fact_templates trong DB) */
export interface FactTypeConfig {
  label: string;
  icon: LucideIcon;
  colorClass: string;
}

export const FACT_TYPE_CONFIG: Record<ClinicalFactType, FactTypeConfig> = {
  symptom: {
    label: "Triệu chứng",
    icon: Activity,
    colorClass:
      "bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-400 border-blue-200 dark:border-blue-800/50",
  },
  lesion: {
    label: "Tổn thương da",
    icon: Microscope,
    colorClass:
      "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-400 border-rose-200 dark:border-rose-800/50",
  },
  history: {
    label: "Tiền sử / Diễn tiến",
    icon: History,
    colorClass:
      "bg-purple-100 text-purple-700 dark:bg-purple-950/50 dark:text-purple-400 border-purple-200 dark:border-purple-800/50",
  },
  medication: {
    label: "Thuốc đang dùng",
    icon: Pill,
    colorClass:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/50",
  },
  allergy: {
    label: "Dị ứng",
    icon: AlertTriangle,
    colorClass:
      "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400 border-amber-200 dark:border-amber-800/50",
  },
  image_finding: {
    label: "Giả thuyết ảnh (AI)",
    icon: ImageIcon,
    colorClass:
      "bg-indigo-100 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800/50",
  },
  other: {
    label: "Khác",
    icon: HelpCircle,
    colorClass:
      "bg-gray-100 text-gray-700 dark:bg-gray-800/50 dark:text-gray-400 border-gray-200 dark:border-gray-700/50",
  },
};

/** Cấu hình hiển thị trạng thái phiên tư vấn (consultation_sessions.status) */
export interface StatusConfig {
  label: string;
  icon: LucideIcon;
  color: string;
  badgeClass: string;
}

export const STATUS_CONFIG: Record<ConsultationStatus, StatusConfig> = {
  pending: {
    label: "Chờ nhận ca",
    icon: Clock,
    color: "text-amber-500 dark:text-amber-400",
    badgeClass:
      "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-400",
  },
  active: {
    label: "Đang tư vấn",
    icon: CircleDot,
    color: "text-emerald-500 dark:text-emerald-400",
    badgeClass:
      "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400",
  },
  resolved: {
    label: "Đã hoàn thành",
    icon: CheckCircle2,
    color: "text-muted-foreground",
    badgeClass: "border-border bg-muted text-muted-foreground",
  },
};

/** Cấu hình nút hành động tiếp quản / đóng phiên tư vấn */
export interface StatusActionConfig {
  label: string;
  icon: LucideIcon;
  buttonClass: string;
  action: "accept" | "resolve" | null;
}

export const STATUS_ACTION_CONFIG: Record<ConsultationStatus, StatusActionConfig> = {
  pending: {
    label: "Nhận ca tư vấn",
    icon: HandHelping,
    buttonClass:
      "bg-gradient-to-r from-brand to-brand-secondary text-brand-foreground hover:shadow-accent",
    action: "accept",
  },
  active: {
    label: "Đóng phiên tư vấn",
    icon: CheckCircle2,
    buttonClass:
      "bg-gradient-to-r from-emerald-500 to-emerald-600 text-white hover:shadow-lg",
    action: "resolve",
  },
  resolved: {
    label: "Phiên đã hoàn tất",
    icon: CheckCircle2,
    buttonClass: "",
    action: null,
  },
};

/** Các lựa chọn lọc ca tư vấn trên thanh sidebar */
export const FILTER_OPTIONS: { value: ConsultationStatus | "all"; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "pending", label: "Chờ nhận" },
  { value: "active", label: "Đang tư vấn" },
  { value: "resolved", label: "Đã đóng" },
];

import { WandSparkles, Search, Stethoscope, Languages, type LucideIcon } from "lucide-react";

/** Giới hạn khi gửi 1 tin nhắn — đồng bộ với core/app/constant/limits.py */
// Trích dẫn: tối đa 1 đoạn / mỗi loại nguồn (1 từ tin nhắn + 1 từ canvas).
export const MAX_SELECTIONS_PER_SOURCE = 1;
export const MAX_SELECTIONS_TOTAL = 2;
export const MAX_ATTACHMENTS = 5;
export const MAX_ATTACHMENT_TOTAL_BYTES = 20 * 1024 * 1024;

export interface ModelOption {
  id: string;
  label: string;
  description: string;
}

export interface SkillOption {
  id: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

/** Danh sách model cho khung nhập chat — `id` PHẢI khớp key trong
 * `core/app/core/config.py::Settings.AGENT_MODEL_CHOICES` (backend chỉ nhận đúng những
 * id này ở `SendMessageInput.modelId`/`CreateConversationInput.model`, id lạ bị bỏ qua
 * lặng lẽ — xem `core/app/services/message_service.py::_apply_model_choice`). Đổi model
 * ở backend thì sửa CẢ 2 nơi. */
export const MODEL_OPTIONS: ModelOption[] = [
  {
    id: "gemma4-26b",
    label: "Gemma 4 26B",
    description: "Cân bằng tốc độ và chất lượng — model mặc định",
  },
  {
    id: "deepseek-v4-pro",
    label: "DeepSeek V4 Pro",
    description: "Phân tích chuyên sâu, đầy đủ các bước suy luận",
  },
  {
    id: "deepseek-v4-flash",
    label: "DeepSeek V4 Flash",
    description: "Phản hồi nhanh, suy luận gọn gàng",
  },
];

/** Danh sách Kỹ năng (Skills) hiển thị khi gõ "/" trong ô nhập chat */
export const SKILL_OPTIONS: SkillOption[] = [
  {
    id: "soan-huong-dan-cham-soc-da",
    label: "Soạn hướng dẫn chăm sóc da",
    description: "Phác đồ điều trị, hướng dẫn dùng thuốc, chăm sóc tại nhà...",
    icon: WandSparkles,
  },
  {
    id: "tra-cuu-tai-lieu-y-khoa",
    label: "Tra cứu tài liệu y khoa",
    description: "Tìm hướng dẫn chẩn đoán, phác đồ điều trị liên quan",
    icon: Search,
  },
  {
    id: "phan-tich-trieu-chung-da",
    label: "Phân tích triệu chứng da",
    description: "Đánh giá tổn thương da và mức độ nghiêm trọng",
    icon: Stethoscope,
  },
  {
    id: "dich-thuat-y-khoa",
    label: "Dịch thuật y khoa",
    description: "Dịch tài liệu, đơn thuốc song ngữ",
    icon: Languages,
  },
];

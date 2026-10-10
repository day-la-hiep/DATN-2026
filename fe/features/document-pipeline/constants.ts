import { Database, FileText, Layers, ListTree, type LucideIcon } from "lucide-react";
import type { StageState, StepId } from "./types";

export const STEP_ORDER: StepId[] = ["ingest", "toc", "chunks", "index"];

export const STEP_INFO: Record<StepId, { label: string; icon: LucideIcon; desc: string; review: string; note?: string }> = {
  ingest: {
    label: "Đọc nội dung",
    icon: FileText,
    desc: "Chuyển file PDF thành văn bản theo từng trang để hệ thống làm việc được với nội dung sách. Sách scan hoặc có chữ bị lỗi sẽ được nhận dạng từ ảnh trang (mất nhiều thời gian hơn). Có thể dừng và tiếp tục sau.",
    note: "Không cần chờ bước này xong mới làm bước Mục lục (mục lục chỉ cần đọc vài chục trang đầu sách), nhưng hệ thống cần đọc cả cuốn để đối chiếu số trang, định vị mục và chia đoạn.",
    review: "Mở vài trang ở khung bên phải để kiểm tra văn bản có được đọc đúng không. Trang không cần dùng (vd phần chỉ mục cuối sách) có thể loại trong Cài đặt.",
  },
  toc: {
    label: "Mục lục",
    icon: ListTree,
    desc: "AI đọc các trang mục lục của sách (không đọc cả cuốn) để dựng cấu trúc Phần → Chương → Bài/Bệnh kèm số trang. Hệ thống tự đối chiếu số trang in trong sách với số trang của file PDF và tìm vị trí tiêu đề của từng mục.",
    review: "Đối chiếu với trang mục lục trong sách: sửa tên, cấp, số trang bị đọc sai (mục cần kiểm tra được tô vàng), xoá dòng thừa, thêm dòng bị bỏ sót.",
  },
  chunks: {
    label: "Chia đoạn",
    icon: Layers,
    desc: "Chia nội dung thành các đoạn ngắn theo đúng cấu trúc mục lục: mỗi đoạn chỉ thuộc một mục, không lẫn sang bệnh hay bài khác. Mỗi đoạn ghi rõ phần, chương, mục và số trang nguồn để tra cứu, trích dẫn.",
    review: "Xem các đoạn theo cây mục lục, kiểm tra đoạn có đúng mục và đúng trang không. Đoạn quá ngắn/dài hoặc có vị trí chưa chắc chắn được đánh dấu “cần xem”.",
  },
  index: {
    label: "Kho tri thức",
    icon: Database,
    desc: "Lưu các đoạn nội dung vào kho tri thức của trợ lý AI để có thể tra cứu theo ý nghĩa. Mỗi đoạn được lưu kèm phần, chương, mục, số trang và vị trí file PDF gốc. Làm lại bước này sẽ thay thế toàn bộ đoạn cũ của sách.",
    note: "Nếu sau này sửa mục lục hoặc chia đoạn lại, hãy làm lại bước này để kho tri thức khớp nội dung mới nhất.",
    review: "Kiểm tra số đoạn đã lưu khớp với số đoạn ở bước Chia đoạn. Sau khi xác nhận, nội dung sách sẵn sàng cho trợ lý AI sử dụng.",
  },
};

export const LEVELS = [
  { v: 0, label: "Phần" },
  { v: 1, label: "Chương" },
  { v: 2, label: "Bài/Bệnh" },
  { v: 3, label: "Mục nhỏ" },
];
export const LEVEL_TONE = ["text-violet-600 dark:text-violet-400", "text-brand", "text-foreground", "text-muted-foreground"];

export const STATE_INFO: Record<StageState, { label: string; tone: string }> = {
  not_started: { label: "Chưa bắt đầu", tone: "bg-muted text-muted-foreground border-border" },
  running: { label: "Đang xử lý", tone: "bg-brand/10 text-brand border-brand/30" },
  pending_review: {
    label: "Chờ xác nhận",
    tone: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30",
  },
  approved: {
    label: "Đã xác nhận",
    tone: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
  },
  failed: { label: "Lỗi", tone: "bg-destructive/10 text-destructive border-destructive/30" },
  cancelled: { label: "Đã dừng", tone: "bg-muted text-muted-foreground border-border" },
  stale: {
    label: "Cần làm lại",
    tone: "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/30",
  },
};

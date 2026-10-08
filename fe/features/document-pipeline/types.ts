// Khớp DTO `core/app/dto/{request,response}/document.py`; wire dùng snake_case.
export type StageState =
  | "not_started"
  | "running"
  | "pending_review"
  | "approved"
  | "failed"
  | "cancelled"
  | "stale";
export type StepId = "ingest" | "toc" | "chunks" | "index";

export interface Progress {
  done: number;
  total: number;
  message: string;
}

export interface Stage {
  stage_id: StepId;
  title: string;
  deps: StepId[];
  uses_llm: boolean;
  state: StageState;
  started_at?: string | null;
  finished_at?: string | null;
  approved_at?: string | null;
  progress?: Progress | null;
  summary?: Record<string, unknown> | null;
  error?: string | null;
  options: Record<string, unknown>;
  /** bước phụ thuộc chưa được duyệt -> chưa chạy được */
  blocked_by: StepId[];
}

/** Khớp `FileDto` (`core/app/dto/common.py`), field theo `File` ở base. */
export interface FileRef {
  file_name: string;
  storage_key: string;
  content_type?: string | null;
  size?: number | null;
  created_at?: string | null;
  url?: string | null;
}

export interface Document {
  id: string;
  title: string;
  created_at?: string | null;
  /** file PDF gốc (khớp `File` ở base); null = chưa có */
  source_file?: FileRef | null;
  pdf_pages?: number | null;
  stages: Stage[];
  running_stage?: StepId | null;
}

export interface DocumentSummary {
  id: string;
  title: string;
  created_at?: string | null;
  states: Record<StepId, StageState>;
}

export interface Settings {
  title: string;
  engine: "pdftotext" | "docling";
  docling_force_ocr: boolean;
  docling_tables: boolean;
  noise_pages: string[];
  llm_enabled: boolean;
  llm_model: string;
  max_tokens: number;
  min_tokens: number;
  boundary_level: number;
  breadcrumb: boolean;
}

export interface TocEntry {
  id: string;
  /** 0 part, 1 section, 2 mục/bệnh, 3 mục con */
  level: number;
  kind: "part" | "section" | "topic" | "sub";
  title: string;
  /** số trang IN của sách theo mục lục; null = không có (part/section thường không có số trang) */
  page_printed?: number | null;
  toc_page?: number | null;
  suspect?: boolean;
  suspect_reason?: string;
  edited?: boolean;
  added?: boolean;
  parent_id?: string | null;
  path: string[];
  /** trang PDF sau khi quy đổi bằng độ lệch */
  page?: number | null;
  anchor_line?: number | null;
  /** true = tìm thấy dòng tiêu đề của mục ở trang đó; false = chỉ biết trang theo mục lục */
  anchored?: boolean;
  /** trang quy đổi vượt quá số trang của bản PDF (bản trích): không thành chunk */
  out_of_range?: boolean;
}

export interface TocDoc {
  toc_pages: number[];
  pages_source: "user" | "llm" | string;
  entries: TocEntry[];
  /** trang PDF = trang in + offset; null = chưa xác định */
  offset?: number | null;
  offset_info: { source?: "user" | "auto"; matched?: number; votes?: Record<string, number>; support?: number };
  total_pages: number;
  anchored: number;
  warnings: string[];
}

export interface TocUpdate {
  items?: { id: string; title?: string; level?: number; page_printed?: number; clear_page?: boolean }[];
  revert?: string[];
  deleted?: string[];
  restored?: string[];
  added?: { title: string; level?: number; page_printed?: number; after_id?: string }[];
  removed_added?: string[];
  offset?: number;
  clear_offset?: boolean;
}

export interface Figure {
  figure_id: string;
  document_id: string;
  page: number;
  seq: number;
  /** [trái, trên, phải, dưới] trên trang PDF */
  bbox?: number[] | null;
  caption: string;
}

export interface Chunk {
  chunk_id: string;
  seq: number;
  text: string;
  context_text: string;
  part: string;
  section: string;
  topic: string;
  subtopic: string;
  toc_path: string[];
  toc_node_ids: string[];
  /** ảnh nằm trong khoảng trang của chunk */
  figure_ids: string[];
  level: number;
  /** khoảng trang PDF theo mục lục của mục chứa chunk */
  pages_hint: [number, number] | null;
  /** mục chưa neo được dòng: ranh giới chỉ chính xác tới cấp trang */
  boundary: boolean;
  suspect: boolean;
  page_start: number;
  page_end: number;
  page_printed_start: number;
  page_printed_end: number;
  tokens: number;
  chars: number;
  review_reason?: string | null;
}

export interface ChunkList {
  items: Chunk[];
  total: number;
  page: number;
  page_size: number;
  counts: { all?: number; review?: number; tokens?: number; per_node?: Record<string, number> };
}

export interface SourcePage {
  page: number;
  page_printed: number;
  header: string;
  text: string;
  noise: boolean;
  noise_reason?: string | null;
  noise_score: number;
}

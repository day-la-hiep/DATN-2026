/**
 * Kiểu dữ liệu của luồng chunk theo mục lục — khớp DTO `core/app/dto/request/toc_pipeline.py + core/app/dto/response/toc_pipeline.py` và record do
 * `core/pipeline/document_ingest` định nghĩa (đã đổi key sang camelCase ở service).
 */
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
  id: StepId;
  title: string;
  deps: StepId[];
  usesLlm: boolean;
  state: StageState;
  startedAt?: string | null;
  finishedAt?: string | null;
  approvedAt?: string | null;
  progress?: Progress | null;
  summary?: Record<string, unknown> | null;
  error?: string | null;
  options: Record<string, unknown>;
  /** bước phụ thuộc chưa được duyệt -> chưa chạy được */
  blockedBy: StepId[];
}

export interface Document {
  id: string;
  title: string;
  createdAt?: string | null;
  hasPdf: boolean;
  pdfPages?: number | null;
  stages: Stage[];
  runningStage?: StepId | null;
}

export interface DocumentSummary {
  id: string;
  title: string;
  createdAt?: string | null;
  states: Record<StepId, StageState>;
}

export interface Settings {
  title: string;
  engine: "pdftotext" | "docling";
  doclingForceOcr: boolean;
  doclingTables: boolean;
  noisePages: string[];
  llmEnabled: boolean;
  llmModel: string;
  maxTokens: number;
  minTokens: number;
  boundaryLevel: number;
  breadcrumb: boolean;
}

export interface TocEntry {
  id: string;
  /** 0 part, 1 section, 2 mục/bệnh, 3 mục con */
  level: number;
  kind: "part" | "section" | "topic" | "sub";
  title: string;
  /** số trang IN của sách theo mục lục; null = không có (part/section thường không có số trang) */
  printedPage?: number | null;
  tocPage?: number | null;
  suspect?: boolean;
  suspectReason?: string;
  edited?: boolean;
  added?: boolean;
  parentId?: string | null;
  path: string[];
  /** trang PDF sau khi quy đổi bằng độ lệch */
  pdfPage?: number | null;
  anchorLine?: number | null;
  /** true = tìm thấy dòng tiêu đề của mục ở trang đó; false = chỉ biết trang theo mục lục */
  anchored?: boolean;
  /** trang quy đổi vượt quá số trang của bản PDF (bản trích): không thành chunk */
  outOfRange?: boolean;
}

export interface TocDoc {
  tocPages: number[];
  pagesSource: "user" | "llm" | string;
  entries: TocEntry[];
  /** trang PDF = trang in + offset; null = chưa xác định */
  offset?: number | null;
  offsetInfo: { source?: "user" | "auto"; matched?: number; votes?: Record<string, number>; support?: number };
  totalPages: number;
  anchored: number;
  warnings: string[];
}

export interface TocUpdate {
  items?: { id: string; title?: string; level?: number; printedPage?: number; clearPage?: boolean }[];
  revert?: string[];
  deleted?: string[];
  restored?: string[];
  added?: { title: string; level?: number; printedPage?: number; afterId?: string }[];
  removedAdded?: string[];
  offset?: number;
  clearOffset?: boolean;
}

export interface Chunk {
  chunkId: string;
  seq: number;
  text: string;
  contextText: string;
  part: string;
  section: string;
  topic: string;
  subtopic: string;
  tocPath: string[];
  tocNodeIds: string[];
  level: number;
  /** khoảng trang PDF theo mục lục của mục chứa chunk */
  pagesHint: [number, number] | null;
  /** mục chưa neo được dòng: ranh giới chỉ chính xác tới cấp trang */
  boundary: boolean;
  suspect: boolean;
  pageStart: number;
  pageEnd: number;
  pagePrintedStart: number;
  pagePrintedEnd: number;
  tokens: number;
  chars: number;
  reviewReason?: string | null;
}

export interface ChunkList {
  items: Chunk[];
  total: number;
  page: number;
  pageSize: number;
  counts: { all?: number; review?: number; tokens?: number; perNode?: Record<string, number> };
}

export interface SourcePage {
  page: number;
  pagePrinted: number;
  header: string;
  text: string;
  noise: boolean;
  noiseReason?: string | null;
  noiseScore: number;
}

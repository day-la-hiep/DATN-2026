import axios from "axios";
import { api } from "@/services/client";
import type {
  Document,
  DocumentSummary,
  Figure,
  ChunkList,
  Settings,
  SourcePage,
  StepId,
  TocDoc,
  TocUpdate,
} from "./types";

/** Thông báo lỗi hiển thị cho người dùng: ưu tiên `detail` của FastAPI. */
export function errorMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
    if (e.code === "ECONNABORTED") return "Quá thời gian chờ phản hồi.";
    if (!e.response) return "Không kết nối được máy chủ.";
    return `Lỗi ${e.response.status}`;
  }
  return e instanceof Error ? e.message : "Đã có lỗi xảy ra.";
}

/** Backend bọc mọi response trong `{ data }` (`ApiResponse`). */
async function unwrap<T>(p: Promise<{ data: { data: T } }>): Promise<T> {
  return (await p).data.data;
}

const root = "/admin/documents";
const base = (documentId: string) => `${root}/documents/${encodeURIComponent(documentId)}`;

export const documentApi = {
  listDocuments: () => unwrap<DocumentSummary[]>(api.get(`${root}/documents`)),

  createDocument: (form: { file: File; title: string; documentId?: string; engine?: string }) => {
    const fd = new FormData();
    fd.append("file", form.file);
    fd.append("title", form.title);
    if (form.documentId) fd.append("documentId", form.documentId);
    if (form.engine) fd.append("engine", form.engine);
    // PDF vài trăm MB: bỏ timeout mặc định; để axios tự đặt boundary multipart
    return unwrap<Document>(api.post(`${root}/documents`, fd, { timeout: 0, headers: { "Content-Type": undefined } }));
  },
  getDocument: (documentId: string) => unwrap<Document>(api.get(base(documentId))),
  deleteDocument: async (documentId: string) => {
    await api.delete(base(documentId));
  },

  getSettings: (documentId: string) => unwrap<Settings>(api.get(`${base(documentId)}/settings`)),
  saveSettings: (documentId: string, body: Settings) => unwrap<Settings>(api.put(`${base(documentId)}/settings`, body)),

  runStage: (documentId: string, stage: StepId, options: Record<string, unknown>) =>
    unwrap<Document>(api.post(`${base(documentId)}/stages/${stage}/run`, { options })),
  cancelStage: (documentId: string, stage: StepId) => unwrap<Document>(api.post(`${base(documentId)}/stages/${stage}/cancel`)),
  approveStage: (documentId: string, stage: StepId) => unwrap<Document>(api.post(`${base(documentId)}/stages/${stage}/approve`)),
  reapplyStage: (documentId: string, stage: StepId) => unwrap<Document>(api.post(`${base(documentId)}/stages/${stage}/reapply`)),
  stageLog: (documentId: string, stage: StepId, lines = 300) =>
    unwrap<string>(api.get(`${base(documentId)}/stages/${stage}/log`, { params: { lines } })),

  page: (documentId: string, page: number) => unwrap<SourcePage>(api.get(`${base(documentId)}/pages/${page}`)),
  /** Ảnh cần header Authorization nên tải bằng axios (blob) rồi dùng object URL. */
  pageImageUrl: async (documentId: string, page: number) => {
    const blob = (await api.get(`${base(documentId)}/pages/${page}/image`, { responseType: "blob", timeout: 0 })).data as Blob;
    return URL.createObjectURL(blob);
  },

  toc: (documentId: string) => unwrap<TocDoc>(api.get(`${base(documentId)}/toc`)),
  updateToc: (documentId: string, body: TocUpdate) => unwrap<Document>(api.patch(`${base(documentId)}/toc`, body)),

  chunks: (documentId: string, p: { q?: string; node?: string; onlyReview?: boolean; page: number; pageSize: number }) =>
    unwrap<ChunkList>(
      api.get(`${base(documentId)}/chunks`, {
        params: { q: p.q || undefined, node: p.node || undefined, onlyReview: p.onlyReview || undefined, page: p.page, pageSize: p.pageSize },
      })
    ),
  figures: (documentId: string) => unwrap<Figure[]>(api.get(`${base(documentId)}/figures`)),
  /** Như ảnh trang: cần Authorization nên tải blob rồi dùng object URL. */
  figureImageUrl: async (documentId: string, figureId: string) => {
    const blob = (await api.get(`${base(documentId)}/figures/${encodeURIComponent(figureId)}/image`, { responseType: "blob", timeout: 0 })).data as Blob;
    return URL.createObjectURL(blob);
  },
  exportChunks: async (documentId: string) =>
    (await api.get(`${base(documentId)}/chunks/export`, { responseType: "blob", timeout: 0 })).data as Blob,
};

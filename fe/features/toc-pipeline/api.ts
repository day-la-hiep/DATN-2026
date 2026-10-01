import axios from "axios";
import { api } from "@/services/client";
import type {
  Book,
  BookSummary,
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

const root = "/admin/toc-pipeline";
const base = (bookId: string) => `${root}/books/${encodeURIComponent(bookId)}`;

export const tocApi = {
  listBooks: () => unwrap<BookSummary[]>(api.get(`${root}/books`)),

  createBook: (form: { file: File; title: string; bookId?: string; engine?: string }) => {
    const fd = new FormData();
    fd.append("file", form.file);
    fd.append("title", form.title);
    if (form.bookId) fd.append("bookId", form.bookId);
    if (form.engine) fd.append("engine", form.engine);
    // PDF vài trăm MB: bỏ timeout mặc định; để axios tự đặt boundary multipart
    return unwrap<Book>(api.post(`${root}/books`, fd, { timeout: 0, headers: { "Content-Type": undefined } }));
  },
  getBook: (bookId: string) => unwrap<Book>(api.get(base(bookId))),
  deleteBook: async (bookId: string) => {
    await api.delete(base(bookId));
  },

  getSettings: (bookId: string) => unwrap<Settings>(api.get(`${base(bookId)}/settings`)),
  saveSettings: (bookId: string, body: Settings) => unwrap<Settings>(api.put(`${base(bookId)}/settings`, body)),

  runStage: (bookId: string, stage: StepId, options: Record<string, unknown>) =>
    unwrap<Book>(api.post(`${base(bookId)}/stages/${stage}/run`, { options })),
  cancelStage: (bookId: string, stage: StepId) => unwrap<Book>(api.post(`${base(bookId)}/stages/${stage}/cancel`)),
  approveStage: (bookId: string, stage: StepId) => unwrap<Book>(api.post(`${base(bookId)}/stages/${stage}/approve`)),
  reapplyStage: (bookId: string, stage: StepId) => unwrap<Book>(api.post(`${base(bookId)}/stages/${stage}/reapply`)),
  stageLog: (bookId: string, stage: StepId, lines = 300) =>
    unwrap<string>(api.get(`${base(bookId)}/stages/${stage}/log`, { params: { lines } })),

  page: (bookId: string, page: number) => unwrap<SourcePage>(api.get(`${base(bookId)}/pages/${page}`)),
  /** Ảnh cần header Authorization nên tải bằng axios (blob) rồi dùng object URL. */
  pageImageUrl: async (bookId: string, page: number) => {
    const blob = (await api.get(`${base(bookId)}/pages/${page}/image`, { responseType: "blob", timeout: 0 })).data as Blob;
    return URL.createObjectURL(blob);
  },

  toc: (bookId: string) => unwrap<TocDoc>(api.get(`${base(bookId)}/toc`)),
  updateToc: (bookId: string, body: TocUpdate) => unwrap<Book>(api.patch(`${base(bookId)}/toc`, body)),

  chunks: (bookId: string, p: { q?: string; node?: string; onlyReview?: boolean; page: number; pageSize: number }) =>
    unwrap<ChunkList>(
      api.get(`${base(bookId)}/chunks`, {
        params: { q: p.q || undefined, node: p.node || undefined, onlyReview: p.onlyReview || undefined, page: p.page, pageSize: p.pageSize },
      })
    ),
  exportChunks: async (bookId: string) =>
    (await api.get(`${base(bookId)}/chunks/export`, { responseType: "blob", timeout: 0 })).data as Blob,
};

"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { errorMessage, tocApi } from "./api";
import type { Book, StepId } from "./types";

export const qk = {
  books: ["toc", "books"] as const,
  book: (id: string) => ["toc", "book", id] as const,
  data: (id: string, kind: string, params?: unknown) => ["toc", id, "data", kind, params] as const,
  dataAll: (id: string) => ["toc", id, "data"] as const,
};

const POLL_MS = 1500;

export function useBooks() {
  return useQuery({
    queryKey: qk.books,
    queryFn: tocApi.listBooks,
    refetchInterval: (q) => (q.state.data?.some((b) => Object.values(b.states).includes("running")) ? POLL_MS : false),
  });
}

/** Trạng thái sách; poll nhanh khi có bước đang chạy để thấy tiến độ và tự cập nhật khi xong. */
export function useBook(bookId: string) {
  return useQuery({
    queryKey: qk.book(bookId),
    queryFn: () => tocApi.getBook(bookId),
    refetchInterval: (q) => (q.state.data?.runningStage ? POLL_MS : false),
  });
}

/** Dữ liệu phân trang/đọc theo bộ lọc; giữ dữ liệu cũ khi đổi tham số để danh sách không nhấp nháy. */
export function useData<T>(bookId: string, kind: string, params: unknown, fn: () => Promise<T>, enabled = true) {
  return useQuery({ queryKey: qk.data(bookId, kind, params), queryFn: fn, placeholderData: keepPreviousData, enabled });
}

/** Sau mọi thay đổi dữ liệu: làm mới trạng thái sách + mọi dữ liệu của sách đó (mục lục, chunk). */
export function useRefreshBook(bookId: string) {
  const qc = useQueryClient();
  return (book?: Book) => {
    if (book) qc.setQueryData(qk.book(bookId), book);
    else qc.invalidateQueries({ queryKey: qk.book(bookId) });
    qc.invalidateQueries({ queryKey: qk.dataAll(bookId) });
    qc.invalidateQueries({ queryKey: qk.books });
  };
}

export function useStageActions(bookId: string) {
  const refresh = useRefreshBook(bookId);
  const onError = (e: unknown) => toast.error(errorMessage(e));
  const run = useMutation({
    mutationFn: (v: { stage: StepId; options?: Record<string, unknown> }) => tocApi.runStage(bookId, v.stage, v.options ?? {}),
    onSuccess: (b) => refresh(b),
    onError,
  });
  const cancel = useMutation({
    mutationFn: (stage: StepId) => tocApi.cancelStage(bookId, stage),
    onSuccess: (b) => {
      refresh(b);
      toast.message("Đã gửi yêu cầu dừng.");
    },
    onError,
  });
  const approve = useMutation({
    mutationFn: (stage: StepId) => tocApi.approveStage(bookId, stage),
    onSuccess: (b) => {
      refresh(b);
      toast.success("Đã xác nhận bước.");
    },
    onError,
  });
  const reapply = useMutation({
    mutationFn: (stage: StepId) => tocApi.reapplyStage(bookId, stage),
    onSuccess: (b) => {
      refresh(b);
      toast.success("Đã đối chiếu lại số trang.");
    },
    onError,
  });
  return { run, cancel, approve, reapply };
}

/** Số trang tự về 1 khi `resetKey` (bộ lọc) đổi — suy ra từ state thay vì đặt lại trong effect (luật react-hooks). */
export function usePage(resetKey: string): [number, (p: number) => void] {
  const [s, setS] = useState({ key: resetKey, page: 1 });
  const page = s.key === resetKey ? s.page : 1;
  return [page, (p) => setS({ key: resetKey, page: p })];
}

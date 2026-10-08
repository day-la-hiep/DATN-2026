"use client";

import { create } from "zustand";
import { toast } from "sonner";
import type {
  ConsultationSession,
  ConsultationStatus,
  DoctorViewMessage,
} from "./types";
import { doctorApi, errorMessage } from "./api";

interface DoctorConsultationState {
  /** Danh sách phiên tư vấn */
  sessions: ConsultationSession[];
  /** ID phiên đang xem */
  activeSessionId: string | null;
  /** Tin nhắn của cuộc hội thoại đang xem */
  messages: DoctorViewMessage[];
  /** Đang tải danh sách */
  loading: boolean;
  /** Đang tải tin nhắn */
  loadingMessages: boolean;
  /** Đang thực hiện hành động (nhận ca / đóng ca) */
  actionLoading: boolean;
  /** Filter theo status */
  statusFilter: ConsultationStatus | "all";

  /** Khởi tạo — load danh sách phiên */
  init: () => Promise<void>;
  /** Chọn phiên tư vấn */
  selectSession: (sessionId: string) => Promise<void>;
  /** Đổi filter status */
  setStatusFilter: (status: ConsultationStatus | "all") => void;
  /** Bác sĩ nhận ca */
  acceptSession: (sessionId: string) => Promise<void>;
  /** Bác sĩ đóng ca */
  resolveSession: (sessionId: string) => Promise<void>;
  /** Bác sĩ gửi tin nhắn phản hồi bệnh nhân */
  sendMessage: (content: string) => Promise<void>;
}

export const useDoctorStore = create<DoctorConsultationState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  loading: false,
  loadingMessages: false,
  actionLoading: false,
  statusFilter: "all",

  async init() {
    set({ loading: true });
    try {
      const sessions = await doctorApi.listSessions();
      set({
        sessions,
        loading: false,
        activeSessionId: sessions[0]?.id ?? null,
      });
      if (sessions[0]) {
        await get().selectSession(sessions[0].id);
      }
    } catch (e) {
      set({ loading: false });
      toast.error(errorMessage(e));
    }
  },

  async selectSession(sessionId) {
    set({ activeSessionId: sessionId, loadingMessages: true });
    const session = get().sessions.find((s) => s.id === sessionId);
    if (!session) {
      set({ loadingMessages: false, messages: [] });
      return;
    }
    try {
      const messages = await doctorApi.getMessages(session.conversationId);
      set({ messages, loadingMessages: false });
    } catch (e) {
      set({ loadingMessages: false });
      toast.error(errorMessage(e));
    }
  },

  setStatusFilter(status) {
    set({ statusFilter: status });
  },

  async acceptSession(sessionId) {
    set({ actionLoading: true });
    try {
      await doctorApi.acceptSession(sessionId);
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === sessionId
            ? {
                ...sess,
                status: "active" as ConsultationStatus,
                doctorId: "doc-current",
                startedAt: new Date().toISOString(),
              }
            : sess
        ),
        actionLoading: false,
      }));
      toast.success("Đã tiếp quản ca tư vấn thành công");
    } catch (e) {
      set({ actionLoading: false });
      toast.error(errorMessage(e));
    }
  },

  async resolveSession(sessionId) {
    set({ actionLoading: true });
    try {
      await doctorApi.resolveSession(sessionId);
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === sessionId
            ? {
                ...sess,
                status: "resolved" as ConsultationStatus,
                resolvedAt: new Date().toISOString(),
              }
            : sess
        ),
        actionLoading: false,
      }));
      toast.success("Đã đóng phiên tư vấn");
    } catch (e) {
      set({ actionLoading: false });
      toast.error(errorMessage(e));
    }
  },

  async sendMessage(content) {
    const trimmed = content.trim();
    if (!trimmed) return;

    const { activeSessionId, sessions } = get();
    const session = sessions.find((s) => s.id === activeSessionId);
    if (!session) return;

    try {
      const sentMessage = await doctorApi.sendDoctorMessage(
        session.id,
        session.conversationId,
        trimmed
      );

      // Cập nhật trạng thái tin nhắn và chuyển ca sang active nếu đang pending
      set((s) => ({
        messages: [...s.messages, sentMessage],
        sessions: s.sessions.map((sess) =>
          sess.id === activeSessionId && sess.status === "pending"
            ? {
                ...sess,
                status: "active" as ConsultationStatus,
                doctorId: "doc-current",
                startedAt: sess.startedAt ?? new Date().toISOString(),
              }
            : sess
        ),
      }));
    } catch (e) {
      toast.error(errorMessage(e));
    }
  },
}));

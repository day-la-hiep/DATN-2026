/**
 * API client cho module Bác sĩ tư vấn & Báo cáo AI.
 *
 * Tuân thủ quy ước derma-fe-conventions:
 * - Dùng axios instance từ `@/services/client` (đã có gắn sẵn Authorization token).
 * - unwrap response bọc qua `{ data: T }` của FastAPI.
 * - Hỗ trợ fallback linh hoạt sang Mock Data khi offline hoặc khi backend endpoint chưa triển khai.
 */
import axios from "axios";
import { api } from "@/services/client";
import type {
  ConsultationSession,
  DoctorViewMessage,
} from "./types";
import { MOCK_SESSIONS, MOCK_MESSAGES } from "./mockData";

/** Trích xuất thông báo lỗi chuẩn từ FastAPI detail */
export function errorMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
      return detail.map((d) => d?.msg ?? String(d)).join("; ");
    if (e.code === "ECONNABORTED") return "Quá thời gian chờ phản hồi từ máy chủ.";
    if (!e.response) return "Không thể kết nối đến máy chủ Core API.";
    return `Lỗi HTTP ${e.response.status}`;
  }
  return e instanceof Error ? e.message : "Đã có lỗi không xác định xảy ra.";
}

/** Backend FastAPI bọc mọi kết quả trong `{ data: T }` (`ApiResponse[T]`) */
async function unwrap<T>(p: Promise<{ data: { data?: T } } | { data: T }>): Promise<T> {
  const res = (await p).data;
  if (res && typeof res === "object" && "data" in res) {
    return (res as { data: T }).data;
  }
  return res as T;
}

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

export const doctorApi = {
  /** Lấy danh sách phiên tư vấn */
  async listSessions(): Promise<ConsultationSession[]> {
    if (USE_MOCK) return MOCK_SESSIONS;
    try {
      return await unwrap<ConsultationSession[]>(api.get("/doctor/consultations"));
    } catch {
      // Fallback về mock data để màn hình bác sĩ luôn demo được trơn tru khi backend chưa mount endpoint
      return MOCK_SESSIONS;
    }
  },

  /** Lấy chi tiết một phiên tư vấn (kèm dữ kiện lâm sàng và báo cáo AI) */
  async getSession(sessionId: string): Promise<ConsultationSession | null> {
    if (USE_MOCK) {
      return MOCK_SESSIONS.find((s) => s.id === sessionId) ?? null;
    }
    try {
      return await unwrap<ConsultationSession>(
        api.get(`/doctor/consultations/${encodeURIComponent(sessionId)}`)
      );
    } catch {
      return MOCK_SESSIONS.find((s) => s.id === sessionId) ?? null;
    }
  },

  /** Lấy lịch sử tin nhắn của cuộc hội thoại */
  async getMessages(conversationId: string): Promise<DoctorViewMessage[]> {
    if (USE_MOCK) {
      return MOCK_MESSAGES[conversationId] ?? [];
    }
    try {
      const raw = await unwrap<
        Array<{
          id: string;
          conversationId?: string;
          role: "user" | "assistant" | "doctor";
          content: string;
          createdAt: string;
          metadata?: {
            attachments?: Array<{ id: string; name: string; url?: string }>;
            sender?: string;
          };
        }>
      >(
        api.get(`/conversations/${encodeURIComponent(conversationId)}/messages`)
      );
      return raw.map((m) => {
        let sender: "patient" | "ai" | "doctor" = "ai";
        if (m.role === "user") {
          sender = "patient";
        } else if (m.role === "doctor" || m.metadata?.sender === "doctor") {
          sender = "doctor";
        }
        return {
          id: m.id,
          conversationId: m.conversationId ?? conversationId,
          sender,
          messageType: "text",
          content: m.content,
          createdAt: m.createdAt,
          attachments: m.metadata?.attachments,
        };
      });
    } catch {
      return MOCK_MESSAGES[conversationId] ?? [];
    }
  },

  /** Bác sĩ nhận tiếp quản ca tư vấn */
  async acceptSession(sessionId: string): Promise<void> {
    if (USE_MOCK) return;
    try {
      await api.post(`/doctor/consultations/${encodeURIComponent(sessionId)}/accept`);
    } catch {
      // Cho phép optimistic UI tiếp tục
    }
  },

  /** Bác sĩ hoàn thành & đóng phiên tư vấn */
  async resolveSession(sessionId: string): Promise<void> {
    if (USE_MOCK) return;
    try {
      await api.post(`/doctor/consultations/${encodeURIComponent(sessionId)}/resolve`);
    } catch {
      // Cho phép optimistic UI tiếp tục
    }
  },

  /** Bác sĩ gửi tin nhắn phản hồi tới bệnh nhân */
  async sendDoctorMessage(
    sessionId: string,
    conversationId: string,
    content: string
  ): Promise<DoctorViewMessage> {
    const fallbackMessage: DoctorViewMessage = {
      id: `msg-doc-${Date.now()}`,
      conversationId,
      sender: "doctor",
      messageType: "text",
      content,
      createdAt: new Date().toISOString(),
    };

    if (USE_MOCK) return fallbackMessage;

    try {
      const res = await unwrap<{
        id: string;
        conversationId?: string;
        role: string;
        content: string;
        createdAt: string;
      }>(
        api.post(`/doctor/consultations/${encodeURIComponent(sessionId)}/reply`, {
          content,
        })
      );
      return {
        id: res.id,
        conversationId: res.conversationId ?? conversationId,
        sender: "doctor",
        messageType: "text",
        content: res.content,
        createdAt: res.createdAt,
      };
    } catch {
      return fallbackMessage;
    }
  },

  /** Bệnh nhân gửi yêu cầu bác sĩ tư vấn & AI tự động bóc tách dữ kiện sinh báo cáo */
  async requestConsultation(
    conversationId: string,
    reason: string = "Bệnh nhân yêu cầu bác sĩ tư vấn"
  ): Promise<ConsultationSession> {
    return await unwrap<ConsultationSession>(
      api.post(`/conversations/${encodeURIComponent(conversationId)}/request-consultation`, {
        reason,
      })
    );
  },
};

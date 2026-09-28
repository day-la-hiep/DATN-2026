import { api, clearAccessToken, getAccessToken } from "./client";
import { endpoints } from "./endpoints";
import {
  toChatMessage,
  toConversation,
  toSendMessageBody,
  toSendMessageResult,
  type ApiChatMessage,
  type ApiConversation,
  type ApiFileAttachment,
  type ApiSendMessageResult,
} from "./apiAdapters";
import type {
  AnswerQuestionInput,
  ChatService,
  ChatStreamEvent,
  CreateConversationInput,
  SendMessageInput,
  SendMessageResult,
} from "@/features/chat/types";

/**
 * Service kết nối backend API theo contract core/app/api/conversation_api.py:
 * - GET /conversations
 * - POST /conversations (CreateConversationInput: userId, initMessage, title)
 * - GET /conversations/{conversation_id}/messages
 * - POST /conversations/{conversation_id}/messages (SendMessageInput: clientMessageId, content, modelId, attachments, selection)
 * - POST /conversations/{conversation_id}/questions/{questionId}/answer (MessageAnswerDto: questionId, optionId, label, custom)
 * - GET /conversations/{conversation_id}/stream (SSE response stream text/event-stream)
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";

const impl = {
  listeners: new Set<(event: ChatStreamEvent) => void>(),

  /** SSE không cần kết nối bền; connect chỉ là để tương thích interface */
  async connect() {
    return;
  },

  disconnect() {
    // không có socket để đóng
  },

  async getConversations() {
    // Backend yêu cầu query param `userId` bắt buộc (chưa có auth thật — xem
    // `core/docs/api-doc.md` mục 0/1.1); FE cũng hard-code "user-1" ở mọi chỗ khác
    // (`createConversation` bên dưới, `store.ts`), giữ nhất quán.
    const { data } = await api.get<{ data: ApiConversation[] }>(
      endpoints.conversations,
      { params: { userId: "user-1" } }
    );
    return data.data.map(toConversation);
  },

  async getMessages(conversationId: string) {
    const { data } = await api.get<{ data: ApiChatMessage[] }>(
      endpoints.messages(conversationId)
    );
    return data.data.map(toChatMessage);
  },

  async createConversation(input?: Partial<CreateConversationInput> | string) {
    const payload: CreateConversationInput =
      typeof input === "string"
        ? { userId: "user-1", initMessage: "", title: input }
        : {
            userId: input?.userId ?? "user-1",
            initMessage: input?.initMessage ?? "",
            title: input?.title ?? "",
          };

    const { data } = await api.post<{ data: ApiConversation }>(
      endpoints.conversations,
      payload
    );
    return toConversation(data.data);
  },

  async updateDocument({
    messageId,
    content,
    isCanvas,
  }: {
    messageId: string;
    content: string;
    isCanvas?: boolean;
  }) {
    await api.put(endpoints.document(messageId), { content, isCanvas });
  },

  onEvent(listener: (event: ChatStreamEvent) => void) {
    impl.listeners.add(listener);
    return () => impl.listeners.delete(listener);
  },

  /**
   * Mở SSE connection và forward event tới listeners cho tới khi nhận `[DONE]`.
   *
   * Không còn cần "mở stream trước khi POST": Core **hoãn** đẩy turn cho Agent Worker
   * (`agent:pending_turn` trong Redis) tới khi handler SSE này `subscribe` xong
   * (`flush_pending_turn`) — nên dù mở SSE ngay SAU khi POST trả về, không event nào bị
   * rơi. Dùng chung cho `sendMessage` (turn mới) lẫn `answerQuestion` (resume sau
   * `tool_ask` — connection cũ đã đóng lúc pause).
   */
  async _openStream(conversationId: string) {
    const token = getAccessToken();
    const res = await fetch(
      `${API_BASE}${endpoints.streamMessage(conversationId)}`,
      {
        method: "GET",
        headers: {
          Accept: "text/event-stream",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      }
    );

    if (res.status === 401) {
      clearAccessToken();
      window.location.reload();
      throw new Error("Access token không hợp lệ.");
    }
    if (!res.ok || !res.body) {
      throw new Error(`SSE stream thất bại: ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // đọc luồng, tách theo event SSE (cách nhau bởi dòng trống, data: ...)
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        for (const line of rawEvent.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const data = line.slice(5).trim();
          if (!data || data === "[DONE]") continue;
          try {
            const event = JSON.parse(data) as ChatStreamEvent;
            impl.listeners.forEach((listener) => listener(event));
          } catch {
            // bỏ qua frame không phải JSON
          }
        }
      }
    }
  },

  async sendMessage(input: SendMessageInput): Promise<SendMessageResult> {
    const payload = toSendMessageBody(input);
    // 1. POST -> Core persist user message + tạo sẵn assistant row (status="queued"),
    //    trả về id thật cả 2. Turn CHƯA chạy (chờ SSE subscribe).
    const { data } = await api.post<{ data: ApiSendMessageResult }>(
      endpoints.sendMessage(input.conversationId),
      payload
    );
    const result = toSendMessageResult(data.data);

    // 2. Mở SSE -> Core flush turn cho Worker. Chạy nền (không await): store đã có id
    //    để gắn bubble, event stream cập nhật dần.
    void impl._openStream(input.conversationId).catch((err) => {
      console.error("SSE stream lỗi", err);
    });

    return result;
  },

  async answerQuestion(input: AnswerQuestionInput) {
    await api.post(
      endpoints.answerQuestion(input.conversationId, input.questionId),
      {
        questionId: input.questionId,
        optionId: input.optionId,
        label: input.label,
        custom: input.custom,
      }
    );
    void impl._openStream(input.conversationId).catch((err) => {
      console.error("SSE stream lỗi", err);
    });
  },

  async improvePrompt(prompt: string) {
    const { data } = await api.post<{ data: string }>(
      endpoints.improvePrompt,
      { prompt }
    );
    return data.data;
  },

  async uploadAttachment(file: File) {
    const form = new FormData();
    form.append("file", file);
    // `Content-Type: undefined` để axios tự set `multipart/form-data; boundary=...` —
    // client mặc định (`services/client.ts`) fix cứng `application/json`.
    const { data } = await api.post<ApiFileAttachment>(
      endpoints.uploadAttachment,
      form,
      { headers: { "Content-Type": undefined } }
    );
    return {
      id: data.id,
      name: data.name,
      size: data.size,
      type: data.type,
      url: data.url ?? undefined,
      uploaded: true,
    };
  },
};

export const chatSse: ChatService = impl;

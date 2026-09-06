import { api } from "./client";
import { endpoints } from "./endpoints";
import {
  toChatMessage,
  toConversation,
  toSendMessageBody,
  type ApiChatMessage,
  type ApiConversation,
} from "./apiAdapters";
import type {
  AnswerQuestionInput,
  ChatService,
  ChatStreamEvent,
  CreateConversationInput,
  SendMessageInput,
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
   * Mở luồng stream SSE TRƯỚC — để Core Backend subscribe Redis Pub/Sub trước khi Agent
   * Worker kịp publish event (tránh mất event đầu luồng) — rồi mới gọi `post`. Dùng chung
   * cho cả `sendMessage` (turn mới/Steer) lẫn `answerQuestion` (resume 1 turn đang tạm
   * dừng chờ `tool_ask` — kết nối SSE cũ đã đóng lúc pause nên bắt buộc phải mở lại).
   */
  async _streamThenPost(conversationId: string, post: () => Promise<unknown>) {
    const res = await fetch(
      `${API_BASE}${endpoints.streamMessage(conversationId)}`,
      {
        method: "GET",
        headers: { Accept: "text/event-stream" },
      }
    );

    if (!res.ok || !res.body) {
      throw new Error(`SSE stream thất bại: ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // Không await trước vòng đọc: lỗi sẽ được bắt sau khi stream kết thúc.
    const postPromise = post().catch((err) => {
      try {
        void reader.cancel();
      } catch {
        /* noop */
      }
      throw err;
    });

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

    // Đảm bảo lỗi từ POST (nếu có) được ném ra ngoài.
    await postPromise;
  },

  async sendMessage(input: SendMessageInput) {
    const payload = toSendMessageBody(input);
    await impl._streamThenPost(input.conversationId, () =>
      api.post(endpoints.sendMessage(input.conversationId), payload)
    );
  },

  async answerQuestion(input: AnswerQuestionInput) {
    await impl._streamThenPost(input.conversationId, () =>
      api.post(endpoints.answerQuestion(input.conversationId, input.questionId), {
        questionId: input.questionId,
        optionId: input.optionId,
        label: input.label,
        custom: input.custom,
      })
    );
  },

  async improvePrompt(prompt: string) {
    const { data } = await api.post<{ data: string }>(
      endpoints.improvePrompt,
      { prompt }
    );
    return data.data;
  },
};

export const chatSse: ChatService = impl;

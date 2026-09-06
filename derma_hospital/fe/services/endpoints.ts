/**
 * Tập trung toàn bộ đường dẫn API ở một nơi.
 * Khi backend thật có sẵn, chỉ cần chỉnh endpoints này.
 */
export const endpoints = {
  conversations: "/conversations",
  messages: (conversationId: string) => `/conversations/${conversationId}/messages`,
  sendMessage: (conversationId: string) => `/conversations/${conversationId}/messages`,
  streamMessage: (conversationId: string) => `/conversations/${conversationId}/stream`,
  /** trả lời 1 câu hỏi (`tool_ask`) agent đang chờ — KHÔNG dùng sendMessage cho việc này */
  answerQuestion: (conversationId: string, questionId: string) =>
    `/conversations/${conversationId}/questions/${questionId}/answer`,
  /** lưu văn bản soạn sẵn (canvas) của một tin nhắn */
  document: (messageId: string) => `/conversations/messages/${messageId}/document`,
  /** cải thiện prompt hiện hành */
  improvePrompt: "/conversations/improve-prompt",
} as const;

import type { ChatService } from "@/features/chat/types";
import { chatSse } from "./chat.sse";
import { mockChatService } from "./mock/mockChatService";

/**
 * Cấu hình chế độ Mock phía Frontend:
 * - NEXT_PUBLIC_USE_MOCK === "true": Inject Client-side Mock Service (mockChatService)
 * - Mặc định (false): Inject Backend API Service thực tế (chatSse qua POST + SSE + REST)
 */
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

/**
 * Factory Provider Inject instance của ChatService tuân thủ Interface ChatService.
 * Sau này khi triển khai thực tế chỉ cần thay đổi cấu hình hoặc thay thế Service tại Factory này.
 */
export function getChatService(useMock: boolean = USE_MOCK): ChatService {
  if (useMock) {
    return mockChatService;
  }
  return chatSse;
}

export const chatService: ChatService = getChatService();

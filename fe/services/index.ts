import type { ChatService } from "@/features/chat/types";
import { chatSse } from "./chat.sse";
import { mockChatService } from "./mock/mockChatService";

// NEXT_PUBLIC_USE_MOCK === "true" dùng mockChatService, mặc định dùng backend thật.
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";


export function getChatService(useMock: boolean = USE_MOCK): ChatService {
  if (useMock) {
    return mockChatService;
  }
  return chatSse;
}

export const chatService: ChatService = getChatService();

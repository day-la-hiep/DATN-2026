export type ChatRole = "user" | "assistant";

export type MessageStatus =
  | "pending"
  | "streaming"
  | "done"
  | "queued"
  | "question";

export type ReasoningStepStatus = "processing" | "done";

export type ReasoningStepType = "default" | "tool_call" | "tool_ask";

export interface ChoiceOption {
  id: string;
  label: string;
}

export interface MessageChoice {
  questionId: string;
  question: string;
  options: ChoiceOption[];
  answered?: { optionId: string; label: string; custom?: boolean };
}

/** Một bước trong chuỗi suy luận của AI */
export interface ReasoningStep {
  id: string;
  /** tiêu đề ngắn gọn của bước, hiển thị khi thu gọn */
  title: string;
  /** nội dung chi tiết, được stream từng token khi mở rộng */
  content: string;
  status: ReasoningStepStatus;
  /** Loại bước suy luận: default (thông thường) hoặc tool_call */
  type?: ReasoningStepType;
  choice?: MessageChoice;
}

/** Tệp đính kèm — chỉ gửi metadata; nội dung file sẽ gửi qua backend sau này */
export interface FileAttachment {
  id: string;
  name: string;
  size: number;
  type: string;
}

/** Văn bản soạn sẵn (document) kèm theo tin nhắn assistant, có thể chỉnh sửa */
export interface ComposedDocument {
  id: string;
  title: string;
  /** nội dung dạng HTML để chỉnh sửa bằng OnlyOffice */
  content: string;
  /** đánh dấu block đã được mở/chỉnh sửa như một canvas */
  isCanvas?: boolean;
}

/** Nguồn của một đoạn trích dẫn kèm tin nhắn ("quote-then-ask") */
export type SelectionSource = "message" | "canvas" | "document";

/** Tham chiếu đoạn được bôi đen khi người dùng hỏi về đoạn đó */
export interface MessageSelectionRef {
  source: SelectionSource;
  /** messageId | canvasId | documentId — tuỳ `source` */
  refId: string;
  /** phiên bản (chỉ với canvas/document) */
  versionNo?: number;
  /** nội dung đoạn được trích */
  text: string;
  /** offset ký tự (tuỳ chọn) */
  start?: number;
  end?: number;
}

export interface ChatMessage {
  id: string;
  conversationId: string;
  role: ChatRole;
  content: string;
  /** Chuỗi các bước lý luận của AI, hiển thị theo danh sách */
  reasoning?: ReasoningStep[];
  /** đoạn tin nhắn được bôi đen mà tin này tham chiếu (hỗ trợ chọn 1 hoặc nhiều đoạn) */
  selectionRef?: MessageSelectionRef | MessageSelectionRef[];
  /** văn bản soạn sẵn kèm tin assistant, có thể chỉnh sửa (canvas) */
  document?: ComposedDocument;
  /** tệp đính kèm (chủ yếu cho tin nhắn của user) */
  attachments?: FileAttachment[];
  createdAt: string;
  status: MessageStatus;
  choice?: MessageChoice;
  isOptionResponse?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export type MessageStatusType =
  | "message.started"
  | "message.steered"
  | "message.delta"
  | "message.done";

export type ReasoningStatusType =
  | "reasoning.step_started"
  | "reasoning.step_completed"
  | "reasoning_step_delta";

export interface ToolMetadata {
  name: string;
}

export interface MessageMetadata {
  status: MessageStatusType;
  content: string;
}

export interface ReasoningMetadata {
  status: ReasoningStatusType;
  title: string;
  content: string;
  toolMetadata?: ToolMetadata;
  stepId?: string;
  stepType?: "default" | "tool_call";
  choice?: MessageChoice;
}

export interface ConversationStreamEvent {
  corr_id?: string | null;
  message_id?: string | null;
  conversation_id: string;
  metadata: MessageMetadata | ReasoningMetadata;
}

export type FlatStreamEvent =
  | {
      type: "message.queued";
      corrId: string;
      conversationId: string;
      messageId: string;
    }
  | {
      type: "message.steered";
      corrId: string;
      conversationId: string;
      messageId: string;
      content: string;
    }
  | {
      type: "message.started";
      corrId: string;
      clientMessageId?: string;
      conversationId: string;
      messageId: string;
    }
  | {
      type: "reasoning.step_started";
      messageId: string;
      conversationId: string;
      stepId: string;
      title: string;
      stepType?: "default" | "tool_call" | "tool_ask";
      choice?: MessageChoice;
    }
  | {
      type: "reasoning.step_delta";
      messageId: string;
      conversationId: string;
      stepId: string;
      delta: string;
    }
  | {
      type: "reasoning.step_completed";
      messageId: string;
      conversationId: string;
      stepId: string;
      stepType?: "default" | "tool_call";
      choice?: MessageChoice;
    }
  | {
      type: "message.delta";
      messageId: string;
      conversationId: string;
      delta: string;
    }
  | {
      type: "message.done";
      messageId: string;
      conversationId: string;
      reasoning?: ReasoningStep[];
    }
  | {
      type: "document.started";
      messageId: string;
      conversationId: string;
      documentId: string;
      title: string;
    }
  | {
      type: "document.delta";
      messageId: string;
      conversationId: string;
      documentId: string;
      delta: string;
    }
  | {
      type: "document.done";
      messageId: string;
      conversationId: string;
      documentId: string;
      document?: ComposedDocument;
    };

/**
 * Các sự kiện stream từ backend (SSE — server push qua POST response).
 */
export type ChatStreamEvent = ConversationStreamEvent | FlatStreamEvent;

/** Câu trả lời cho câu hỏi agent đã đưa ra */
export interface MessageAnswer {
  questionId: string;
  optionId: string;
  label: string;
  custom?: boolean;
}

export interface CreateConversationInput {
  userId: string;
  initMessage: string;
  title?: string;
}

/** Input nội bộ store → chatService. Adapter (services/apiAdapters.ts) map sang wire body. */
export interface SendMessageInput {
  conversationId: string;
  corrId: string;
  clientMessageId?: string;
  content: string;
  modelId?: string;
  attachments?: FileAttachment[];
  selection?: MessageSelectionRef | MessageSelectionRef[];
}

/** Input trả lời 1 câu hỏi agent đang chờ — đi qua endpoint riêng
 * `POST /conversations/{id}/questions/{questionId}/answer`, KHÔNG qua sendMessage. */
export type AnswerQuestionInput = MessageAnswer & { conversationId: string };

export interface ChatService {
  connect(): Promise<void>;
  disconnect(): void;
  getConversations(): Promise<Conversation[]>;
  getMessages(conversationId: string): Promise<ChatMessage[]>;
  createConversation(input?: Partial<CreateConversationInput> | string): Promise<Conversation>;
  sendMessage(input: SendMessageInput): Promise<void> | void;
  answerQuestion(input: AnswerQuestionInput): Promise<void> | void;
  updateDocument(input: {
    messageId: string;
    content: string;
    isCanvas?: boolean;
  }): Promise<void> | void;
  onEvent(listener: (event: ChatStreamEvent) => void): () => void;
  improvePrompt(prompt: string): Promise<string>;
}

/**
 * Adapter: DTO trên wire của Core Backend (camelCase — mọi response DTO kế thừa
 * `CamelModel`, xem `core/app/dto/common.py`/`core/app/dto/message.py`/
 * `core/app/dto/conversation.py`) <-> model nội bộ của store Frontend.
 *
 * Store + component giữ nguyên `ChatMessage` phẳng; chỉ tầng service này biết cấu trúc
 * `metadata` đa hình của backend.
 */
import {
  MAX_ATTACHMENTS,
} from "@/features/chat/constants";
import type {
  ChatMessage,
  ChatRole,
  ChatStreamEvent,
  Conversation,
  FileAttachment,
  MessageChoice,
  MessageStatus,
  ReasoningStep,
  ReasoningStepStatus,
  ReasoningStepType,
  SendMessageInput,
  SendMessageResult,
} from "@/features/chat/types";

/* ----------------------------- Wire DTOs ----------------------------- */
/* Wire dùng snake_case đúng tên field Python của backend; kiểu UI (`features/chat/types.ts`) giữ camelCase —
 * mọi chuyển đổi nằm ở file này. */

export interface ApiConversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

/** Khớp `FileDto` (`core/app/dto/common.py`) — field theo `File` ở `core/app/dto/base/file.py`. */
export interface ApiFileAttachment {
  file_name: string;
  storage_key: string;
  content_type?: string | null;
  size?: number | null;
  created_at?: string | null;
  url?: string | null;
}

/** Wire (`FileDto`) -> kiểu UI `FileAttachment` (UI giữ tên cũ `id/name/type`, chỉ adapter biết tên wire). */
export function toFileAttachment(f: ApiFileAttachment): FileAttachment {
  return {
    id: f.storage_key,
    name: f.file_name,
    size: f.size ?? 0,
    type: f.content_type ?? "",
    url: f.url ?? undefined,
    uploaded: true,
  };
}

/** Khớp `MessageChoiceDto` (`core/app/dto/response/message.py`). */
export interface ApiMessageChoice {
  question_id: string;
  question: string;
  options: { id: string; label: string }[];
  answered?: { option_id: string; label: string; custom?: boolean } | null;
}

export function toMessageChoice(c: ApiMessageChoice): MessageChoice {
  return {
    questionId: c.question_id,
    question: c.question,
    options: c.options,
    answered: c.answered
      ? { optionId: c.answered.option_id, label: c.answered.label, custom: c.answered.custom }
      : undefined,
  };
}

export interface ApiReasoningStep {
  id?: string | null;
  title?: string;
  content?: string;
  input?: unknown;
  status?: string;
  type?: string;
  choice?: ApiMessageChoice | null;
}

/** Khớp `MessageMetadataDto` (`core/app/dto/response/message.py`) — 1 shape dùng chung cho cả
 * message user lẫn assistant, field nào không áp dụng thì `undefined`. */
export interface ApiMessageMetadata {
  reasoning?: ApiReasoningStep[] | null;
  attached_files?: ApiFileAttachment[] | null;
  choice?: ApiMessageChoice | null;
  is_option_response?: boolean | null;
}

export interface ApiChatMessage {
  id: string;
  conversation_id: string;
  /** `MessageSender` (`core/app/common/constant.py`) */
  sender: "patient" | "ai" | "doctor";
  content: string;
  status: MessageStatus;
  metadata?: ApiMessageMetadata | null;
  created_at: string;
}

/** Khớp `SendMessageResult` (`core/app/dto/response/message.py`) — response của
 * `POST /conversations/{id}/messages`. */
export interface ApiSendMessageResult {
  user_message: ApiChatMessage;
  assistant_message: ApiChatMessage;
}

/** Khớp `SendMessageInput` (`core/app/dto/request/message.py`) verbatim — không có
 * `metadata`/`answer`, `attached_files` nằm top-level. */
export interface ApiSendMessageBody {
  client_message_id: string;
  content: string;
  model_id?: string;
  attached_files?: ApiFileAttachment[];
}

/* ----------------------------- Mappers ------------------------------ */

export function toConversation(a: ApiConversation): Conversation {
  return {
    id: a.id,
    title: a.title ?? "",
    createdAt: a.created_at,
    updatedAt: a.updated_at ?? a.created_at,
  };
}

export function toChatMessage(a: ApiChatMessage): ChatMessage {
  // UI chưa có giao diện riêng cho tin bác sĩ (luồng tư vấn làm sau) — tạm hiển thị như tin trả lời
  const role: ChatRole = a.sender === "patient" ? "user" : "assistant";
  const meta = a.metadata ?? undefined;

  const reasoning: ReasoningStep[] | undefined = meta?.reasoning
    ? meta.reasoning.map((s, i) => ({
        id: s.id ?? `${a.id}-step-${i + 1}`,
        title: s.title ?? "Suy luận",
        content: s.content ?? "",
        input: s.input,
        status: (s.status as ReasoningStepStatus) ?? "done",
        type: (s.type as ReasoningStepType) ?? "default",
        choice: s.choice ? toMessageChoice(s.choice) : undefined,
      }))
    : undefined;

  return {
    id: a.id,
    conversationId: a.conversation_id,
    role,
    content: a.content ?? "",
    createdAt: a.created_at,
    // Giữ nguyên status thật từ backend ("question"/"pending"/"queued"...) — KHÔNG
    // hard-code "done", để UI khôi phục đúng trạng thái khi F5 giữa chừng 1 turn.
    status: a.status,
    reasoning,
    choice: meta?.choice ? toMessageChoice(meta.choice) : undefined,
    isOptionResponse: meta?.is_option_response ?? undefined,
    attachments:
      role === "user" && meta?.attached_files ? meta.attached_files.map(toFileAttachment) : undefined,
  };
}

export function toSendMessageResult(a: ApiSendMessageResult): SendMessageResult {
  return {
    userMessage: toChatMessage(a.user_message),
    assistantMessage: toChatMessage(a.assistant_message),
  };
}

export function toSendMessageBody(input: SendMessageInput): ApiSendMessageBody {
  const attachedFiles: ApiFileAttachment[] | undefined = input.attachments
    ?.slice(0, MAX_ATTACHMENTS)
    .map((x) => ({ storage_key: x.id, file_name: x.name, size: x.size, content_type: x.type }));

  return {
    // Backend yêu cầu `client_message_id` bắt buộc — store hiện chỉ set `corrId`, fallback
    // sang đó để không phải sửa mọi call site.
    client_message_id: input.clientMessageId ?? input.corrId,
    content: input.content,
    model_id: input.modelId,
    attached_files: attachedFiles,
  };
}

/** Khoá envelope snake_case của event SSE -> tên trong kiểu UI `FlatStreamEvent`. */
const STREAM_EVENT_KEYS: Record<string, string> = {
  conversation_id: "conversationId",
  message_id: "messageId",
  corr_id: "corrId",
  client_message_id: "clientMessageId",
  step_id: "stepId",
  step_type: "stepType",
  document_id: "documentId",
};

/** Event SSE từ Core (snake_case, `agent/turn.py`, `agent/middleware/*.py`) -> `ChatStreamEvent` của UI. */
export function toStreamEvent(raw: Record<string, unknown>): ChatStreamEvent {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (k === "choice" && v && typeof v === "object") out.choice = toMessageChoice(v as ApiMessageChoice);
    else out[STREAM_EVENT_KEYS[k] ?? k] = v;
  }
  return out as unknown as ChatStreamEvent;
}
